"""Manual, resumable migration of the three explicitly approved Backend A resources.

Uses the existing deployed ZIP, never rebuilds from a dirty working tree. No seed,
application migration, B/AI/Fabric engine, shared lock change or local DB operation.
Private backups use Windows DPAPI and the operator-only state directory.
"""

import argparse
import ctypes
import hashlib
import ipaddress
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from scripts import azure_deploy as cloud

ROOT = cloud.ROOT
WORK = ROOT / ".cache/azure-migration"
OLD_STATE = ROOT / ".cache/azure-team-dev"
NEW_STATE = ROOT / ".cache/azure-backend-a"
OLD_APP, OLD_PG, OLD_PLAN = "csflow-a-dev-api-6004dca5", "csflow-a-dev-pg-6004dca5", "csflow-a-dev-plan"
NEW_APP, NEW_PG, NEW_PLAN = "csflow-backend-a", "csflow-backend-a-pg", "csflow-backend-a-plan"
PG_BIN = None
SCRATCH = None


def check(condition, code):
    if not condition:
        raise RuntimeError(code)


def save(name, value):
    (WORK / name).write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def load(name):
    return json.loads((WORK / name).read_text(encoding="utf-8"))


def crypt(data, *, decrypt=False):
    check(os.name == "nt", "WINDOWS_DPAPI_REQUIRED_FOR_THIS_BACKUP")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    lib = ctypes.windll.crypt32
    operation = lib.CryptUnprotectData if decrypt else lib.CryptProtectData
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError("DPAPI_OPERATION_FAILED")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


def private_backup(name, data):
    folder = WORK / "backups"
    cloud.private_directory(folder)
    path = folder / name
    check(not path.exists(), "BACKUP_ALREADY_EXISTS_NO_OVERWRITE")
    encrypted = crypt(data)
    check(crypt(encrypted, decrypt=True) == data, "BACKUP_DECRYPTION_SELF_CHECK_FAILED")
    path.write_bytes(encrypted)
    return {
        "file": "backups/" + name,
        "plaintext_sha256": hashlib.sha256(data).hexdigest(),
        "encrypted_sha256": hashlib.sha256(encrypted).hexdigest(),
        "bytes": len(encrypted),
        "encryption": "Windows current-user DPAPI",
        "decrypt_roundtrip": True,
    }


@contextmanager
def resource_config(*, target):
    old = cloud.APP, cloud.PG, cloud.PLAN
    cloud.APP, cloud.PG, cloud.PLAN = (NEW_APP, NEW_PG, NEW_PLAN) if target else (OLD_APP, OLD_PG, OLD_PLAN)
    try:
        yield
    finally:
        cloud.APP, cloud.PG, cloud.PLAN = old


def target_config():
    return resource_config(target=True)


def resource(kind, *, target=False):
    name = {
        "app": NEW_APP if target else OLD_APP,
        "postgres": NEW_PG if target else OLD_PG,
        "plan": NEW_PLAN if target else OLD_PLAN,
    }[kind]
    return (
        cloud.BASE
        + {
            "app": "Microsoft.Web/sites/",
            "postgres": "Microsoft.DBforPostgreSQL/flexibleServers/",
            "plan": "Microsoft.Web/serverfarms/",
        }[kind]
        + name
    )


def observed_ip():
    events = cloud.az(
        "monitor",
        "activity-log",
        "list",
        "--resource-id",
        resource("app"),
        "--offset",
        "12h",
        "--max-events",
        "200",
        "--subscription",
        cloud.SUBSCRIPTION,
    )
    address = next(
        (
            (e.get("httpRequest") or {}).get("clientIpAddress")
            for e in events
            if (e.get("httpRequest") or {}).get("clientIpAddress")
        ),
        None,
    )
    check(bool(address), "CURRENT_OPERATOR_IP_UNAVAILABLE")
    return str(ipaddress.IPv4Address(address))


def open_access(*, target=False):
    ip = observed_ip()
    path = resource("postgres", target=target) + "/firewallRules/backend-a-verification-temporary"
    cloud.rest(WORK, "put", path, "2024-08-01", {"properties": {"startIpAddress": ip, "endIpAddress": ip}})


def close_access(*, target=False):
    path = resource("postgres", target=target) + "/firewallRules/backend-a-verification-temporary"
    with resource_config(target=target):
        return cloud.close_operator_firewall(WORK, path)


def url(*, target=False, database="backend_a"):
    values = cloud.state(NEW_STATE if target else OLD_STATE)
    with resource_config(target=target):
        base = make_url(cloud.database_url(values, local=True))
    return base.set(database=database).update_query_dict({"application_name": "backend-a-migration"})


@contextmanager
def engine(*, target=False, database="backend_a"):
    value = url(target=target, database=database)
    db = create_engine(
        value,
        hide_parameters=True,
        echo=False,
        connect_args={"connect_timeout": 15, "options": "-c timezone=UTC -c statement_timeout=120000"},
    )
    try:
        yield db
    finally:
        db.dispose()


def canonical_constraint(definition):
    """Only canonicalize identical casts of flat constant varchar arrays to text.

    PostgreSQL deparse/reparse can distribute an array cast into its elements.
    Names, values, types with lengths, columns, predicates, FKs and validation
    flags remain strict. This is not general SQL whitespace/schema normalization.
    """
    literal = r"'(?:''|[^'])*'"
    item = literal + r"::character varying"
    pattern = r"\(ARRAY\[(" + item + r"(?:, " + item + r")*)\]\)::text\[\]"

    def replace_array(match):
        values = re.findall(literal, match.group(1))
        return "ARRAY[" + ", ".join(v + "::text" for v in values) + "]"

    result = re.sub(pattern, replace_array, definition)
    return re.sub(r"\((" + literal + r")::character varying\)::text", r"\1::text", result)


def fingerprint(connection):
    tables = connection.execute(
        text("""SELECT schemaname,tablename FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2""")
    ).all()
    rows = {}
    for schema, name in tables:
        # All identifiers come from this dedicated DB's catalog, never a request.
        identifier = '"' + schema.replace('"', '""') + '"."' + name.replace('"', '""') + '"'
        item = connection.execute(
            text(f"""SELECT count(*), md5(coalesce(string_agg(h,'' ORDER BY h),''))
            FROM (SELECT md5(row_to_json(t)::text) h FROM {identifier} t) hashes""")
        ).one()
        rows[schema + "." + name] = {"count": item[0], "hash": item[1]}
    sequences = {}
    for schema, name in connection.execute(
        text("""SELECT sequence_schema,sequence_name FROM information_schema.sequences
         WHERE sequence_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1,2""")
    ):
        identifier = '"' + schema.replace('"', '""') + '"."' + name.replace('"', '""') + '"'
        state = connection.execute(text(f"SELECT last_value,is_called FROM {identifier}")).one()
        sequences[schema + "." + name] = {"last_value": state[0], "is_called": state[1]}
    catalogs = {}
    statements = {
        "constraints": "SELECT n.nspname,c.relname,k.conname,k.contype,k.convalidated,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,3",
        "indexes": "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,3",
        "triggers": "SELECT n.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,3",
        "owners_acl": "SELECT n.nspname,c.relname,c.relkind,pg_get_userbyid(c.relowner),c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND c.relkind IN ('r','S','v','m','p') ORDER BY 1,2",
        "table_grants": "SELECT table_schema,table_name,grantor,grantee,privilege_type,is_grantable FROM information_schema.role_table_grants WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,3,4,5",
        "functions": "SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_userbyid(p.proowner),md5(pg_get_functiondef(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND p.prokind IN ('f','p') ORDER BY 1,2,3",
        "schemas": "SELECT nspname,pg_get_userbyid(nspowner),nspacl::text FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname!='information_schema' ORDER BY 1",
    }
    for key, statement in statements.items():
        values = [list(r) for r in connection.execute(text(statement))]
        if key == "constraints":
            values = [[*row[:-1], canonical_constraint(row[-1])] for row in values]
        catalogs[key] = {
            "count": len(values),
            "hash": hashlib.sha256(json.dumps(values, default=str).encode()).hexdigest(),
        }
    return {
        "tables": rows,
        "sequences": sequences,
        "catalogs": catalogs,
        "migration": connection.scalar(text("SELECT version_num FROM alembic_version")),
        "automation_control": json.loads(
            json.dumps(
                dict(connection.execute(text("SELECT * FROM automation_control")).mappings().one()),
                default=str,
            )
        ),
    }


def pg_tool(tool, arguments, *, target=False, database="backend_a"):
    check(PG_BIN is not None, "PG_BIN_REQUIRED")
    value = url(target=target, database=database)
    # Native Windows PostgreSQL tools/libpq require ASCII paths here.
    password_file = SCRATCH / "pgpass.private"

    def escape(value):
        return value.replace("\\", "\\\\").replace(":", "\\:")

    password_file.write_text(
        ":".join(escape(str(v)) for v in (value.host, value.port, database, value.username, value.password))
        + "\n"
    )
    password_file.chmod(0o600)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PG")}
    env.update(
        PGHOST=value.host,
        PGPORT=str(value.port),
        PGDATABASE=database,
        PGUSER=value.username,
        PGPASSFILE=str(password_file),
        PGSSLMODE="verify-full",
        PGSSLROOTCERT=value.query["sslrootcert"],
        PGAPPNAME="backend-a-migration",
    )
    try:
        result = subprocess.run([str(PG_BIN / (tool + ".exe")), *arguments], env=env, capture_output=True)
        if result.returncode:
            error = result.stderr.decode("utf-8", errors="replace")
            diagnosis = "UNCLASSIFIED"
            for pattern, label in [
                ('schema "public" does not exist', "MISSING_STANDARD_PUBLIC_SCHEMA"),
                ("permission denied", "PERMISSION_DENIED"),
                ("unrecognized configuration parameter", "UNSUPPORTED_GUC"),
                ("already exists", "OBJECT_ALREADY_EXISTS"),
                ("must be owner", "OBJECT_OWNER_MISMATCH"),
            ]:
                if pattern in error:
                    diagnosis = label
                    break
            save("pg-tool-error.json", {"tool": tool, "exit": result.returncode, "class": diagnosis})
        check(result.returncode == 0, tool.upper() + "_FAILED_EXIT_" + str(result.returncode))
        return result.stdout
    finally:
        password_file.unlink(missing_ok=True)


def baseline_row_hashes(connection):
    result = {}
    for schema, name in connection.execute(
        text(
            "SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2"
        )
    ):
        columns = list(
            connection.scalars(
                text("""SELECT a.attname FROM pg_index i
             JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace
             CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,position)
             JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
             WHERE i.indisprimary AND n.nspname=:schema AND c.relname=:name ORDER BY k.position"""),
                {"schema": schema, "name": name},
            )
        )
        check(bool(columns), "TABLE_WITHOUT_REVIEWED_PRIMARY_KEY")

        def quote(value):
            return '"' + value.replace('"', '""') + '"'

        identifier = quote(schema) + "." + quote(name)
        keys = ",".join("t." + quote(c) for c in columns)
        rows = [
            list(r)
            for r in connection.execute(
                text(f"SELECT jsonb_build_array({keys}),md5(row_to_json(t)::text) FROM {identifier} t")
            )
        ]
        result[schema + "." + name] = {"pk": columns, "rows": rows}
    return result


def dump(label, *, target=False):
    plain = SCRATCH / (label + ".temporary.dump")
    check(not plain.exists(), "PLAINTEXT_BACKUP_TARGET_ALREADY_EXISTS")
    try:
        pg_tool("pg_dump", ["--format=custom", "--no-owner", "--file", str(plain)], target=target)
        toc = pg_tool("pg_restore", ["--list", str(plain)], target=target)
        result = private_backup(label + ".dump.dpapi", plain.read_bytes())
        result["toc_sha256"] = hashlib.sha256(toc).hexdigest()
        return result
    finally:
        plain.unlink(missing_ok=True)


def backup():
    check(not (WORK / "initial-backup.json").exists(), "INITIAL_BACKUP_ALREADY_COMPLETE")
    open_access()
    try:
        with engine() as db, db.connect() as connection:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            baseline = fingerprint(connection)
            check(
                baseline["migration"] == "0006" and baseline["automation_control"]["paused"],
                "SOURCE_HEAD_OR_PAUSE_MISMATCH",
            )
            roles = (
                connection.execute(
                    text(
                        "SELECT rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolreplication,rolbypassrls,rolconnlimit,rolvaliduntil,rolconfig FROM pg_roles WHERE rolname NOT LIKE 'pg_%' AND rolname NOT LIKE 'azure%' ORDER BY rolname"
                    )
                )
                .mappings()
                .all()
            )
            check(
                {r["rolname"] for r in roles} <= {"csflow_a_owner", "csflow_a_api", "replication"},
                "UNREVIEWED_CUSTOM_DB_ROLE",
            )
            clients = connection.execute(
                text(
                    "SELECT usename,backend_type,count(*) FROM pg_stat_activity WHERE datname=current_database() GROUP BY 1,2"
                )
            ).all()
            private = {"roles": [dict(r) for r in roles], "clients": [list(r) for r in clients]}
        save("initial-fingerprint.json", baseline)
        files = [dump("initial")]
        for name in (
            "source-appsettings.private.json",
            "source-web-config.private.json",
            "source-resources.private.json",
        ):
            path = WORK / name
            files.append(private_backup(name + ".dpapi", path.read_bytes()))
            path.unlink()
        files.append(
            private_backup("database-roles.private.json.dpapi", json.dumps(private, default=str).encode())
        )
        save(
            "initial-backup.json",
            {
                "files": files,
                "source_table_count": len(baseline["tables"]),
                "source_clients": sum(r[2] for r in clients),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        print("Initial encrypted DB/config/role backup verified; source continues running", flush=True)
    finally:
        close_access()


def settings_backup(name):
    path = WORK / "backups" / (name + ".dpapi")
    return json.loads(crypt(path.read_bytes(), decrypt=True))


def provision():
    check(
        not (WORK / "target-write-validation-started.json").exists(),
        "ALREADY_CUT_OVER_USE_NORMAL_DEPLOYMENT_TOOL",
    )
    check((WORK / "initial-backup.json").exists(), "RECOVERABLE_BACKUP_REQUIRED")
    cloud.private_directory(NEW_STATE)
    if not (NEW_STATE / "secrets.json").exists():
        values = cloud.state(OLD_STATE)
        settings = settings_backup("source-appsettings.private.json")["properties"]
        values.update(
            db_admin=secrets.token_urlsafe(48),
            db_runtime=secrets.token_urlsafe(48),
            jwt=settings["JWT_SECRET"],
            service=settings["ANALYTICS_SERVICE_SECRET"],
        )
        (NEW_STATE / "secrets.json").write_text(json.dumps(values))
    plans = cloud.az("appservice", "plan", "list", "-g", cloud.GROUP, "--subscription", cloud.SUBSCRIPTION)
    if not any(p["name"] == NEW_PLAN for p in plans):
        cloud.az(
            "appservice",
            "plan",
            "create",
            "-g",
            cloud.GROUP,
            "-n",
            NEW_PLAN,
            "--location",
            "koreacentral",
            "--is-linux",
            "--sku",
            "B1",
            "--number-of-workers",
            "1",
            "--tags",
            *[f"{k}={v}" for k, v in cloud.TAGS.items()],
            "--subscription",
            cloud.SUBSCRIPTION,
        )
    with target_config():
        cloud.provision(NEW_STATE)
        cloud.configure(NEW_STATE)
    settings = settings_backup("source-appsettings.private.json")["properties"]
    values = cloud.state(NEW_STATE)
    with target_config():
        settings["DATABASE_URL"] = cloud.database_url(values, runtime=True)
    settings["ALLOWED_HOSTS"] = json.dumps(
        [
            NEW_APP + ".azurewebsites.net" if h == OLD_APP + ".azurewebsites.net" else h
            for h in json.loads(settings["ALLOWED_HOSTS"])
        ]
    )
    cloud.rest(
        WORK,
        "put",
        resource("app", target=True) + "/config/appsettings",
        "2024-11-01",
        {"properties": settings},
    )
    print(
        "Target dedicated plan/API/PostgreSQL configured; no seed or application migration executed",
        flush=True,
    )


def freeze_copy():
    check(not (WORK / "copy-verified.json").exists(), "COPY_ALREADY_VERIFIED_NO_OVERWRITE")
    check((WORK / "target-prebuilt.json").exists(), "TARGET_PREBUILD_REQUIRED_BEFORE_OUTAGE")
    check(
        cloud.rest(WORK, "get", resource("app", target=True), "2024-11-01")["properties"]["state"]
        == "Stopped",
        "TARGET_MUST_BE_STOPPED_DURING_COPY",
    )
    current_settings = cloud.rest(WORK, "post", resource("app") + "/config/appsettings/list", "2024-11-01")[
        "properties"
    ]
    check(
        current_settings == settings_backup("source-appsettings.private.json")["properties"],
        "SOURCE_SETTINGS_CHANGED_AFTER_BACKUP_NO_CUTOVER",
    )
    open_access()
    open_access(target=True)
    frozen = False
    try:
        cloud.az("webapp", "stop", "-g", cloud.GROUP, "-n", OLD_APP, "--subscription", cloud.SUBSCRIPTION)
        old = cloud.owned(cloud.rest(WORK, "get", resource("app"), "2024-11-01"))
        check(old["properties"]["state"] == "Stopped", "OLD_APP_NOT_STOPPED")
        frozen = True
        with engine() as db, db.begin() as connection:
            connection.execute(text("ALTER ROLE csflow_a_api NOLOGIN"))
            connection.execute(text("REVOKE CONNECT ON DATABASE backend_a FROM csflow_a_api"))
            connection.execute(text("REVOKE CONNECT ON DATABASE backend_a FROM PUBLIC"))
            connection.execute(text("ALTER DATABASE backend_a SET default_transaction_read_only=on"))
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND usename IN ('csflow_a_api','csflow_a_owner')"
                )
            )
        frozen = True
        # Drain again after the catalog changes committed, closing a login that
        # raced the first termination scan. NOLOGIN blocks subsequent runtime logins.
        with engine() as db, db.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND usename IN ('csflow_a_api','csflow_a_owner')"
                )
            )
            check(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND usename IN ('csflow_a_api','csflow_a_owner')"
                    )
                )
                == 0,
                "SOURCE_CLIENTS_NOT_DRAINED",
            )
        save(
            "write-fence.json",
            {
                "old_app": "Stopped",
                "old_runtime_role": "NOLOGIN",
                "old_database_default_read_only": True,
                "old_runtime_and_owner_other_sessions_terminated": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        with engine() as db, db.connect() as connection:
            source = fingerprint(connection)
            old_rows = baseline_row_hashes(connection)
            from scripts.azure_bootstrap import cloud_id

            customer = cloud_id("customer1/profile")
            fixture_ids = {}
            for key, statement in {
                "ticket": "SELECT ticket_id FROM tickets WHERE customer_id=:customer ORDER BY created_at LIMIT 1",
                "active_ticket": "SELECT ticket_id FROM tickets WHERE customer_id=:customer AND status='IN_PROGRESS' ORDER BY created_at LIMIT 1",
                "resolved_ticket": "SELECT ticket_id FROM tickets WHERE customer_id=:customer AND status='RESOLVED' ORDER BY created_at LIMIT 1",
                "followup": "SELECT f.action_id FROM followup_actions f JOIN tickets t ON t.ticket_id=f.ticket_id WHERE t.customer_id=:customer AND f.public_note IS NOT NULL ORDER BY f.created_at LIMIT 1",
            }.items():
                fixture_ids[key] = str(connection.scalar(text(statement), {"customer": customer}) or "")
            schema_owner = connection.scalar(
                text("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'")
            )
        save("frozen-source-fingerprint.json", source)
        attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        final = dump("final-frozen-" + attempt)
        save("final-backup.json", final)
        row_backup = private_backup(
            "source-row-hashes-" + attempt + ".private.json.dpapi", json.dumps(old_rows, default=str).encode()
        )
        save("baseline-row-backup.json", row_backup)
        fixture_backup = private_backup(
            "existing-http-fixtures-" + attempt + ".private.json.dpapi", json.dumps(fixture_ids).encode()
        )
        save("existing-fixture-backup.json", fixture_backup)
        from psycopg import sql

        values = cloud.state(NEW_STATE)
        with engine(target=True) as db, db.begin() as connection:
            tables = connection.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public'"))
            check(
                tables == 0
                or (
                    (WORK / "target-restore-started.json").exists()
                    and not (WORK / "target-write-validation-started.json").exists()
                ),
                "TARGET_DATABASE_NOT_EMPTY",
            )
            save(
                "target-restore-started.json",
                {
                    "target_id": resource("postgres", target=True),
                    "archive_sha256": final["plaintext_sha256"],
                    "target_app_stopped": True,
                    "public_target_writes_have_never_started": True,
                },
            )
            raw = connection.connection.driver_connection
            with raw.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='csflow_a_api'")
                if not cursor.fetchone():
                    cursor.execute(
                        "CREATE ROLE csflow_a_api LOGIN PASSWORD "
                        + sql.Literal(values["db_runtime"]).as_string(raw)
                    )
                # Only an empty or this tool's unexposed failed copy on the NEW
                # dedicated server. Never source/shared/previous public writes.
                cursor.execute("DROP SCHEMA IF EXISTS public CASCADE")
                # This archive expects the standard public schema to exist.
                cursor.execute("CREATE SCHEMA public AUTHORIZATION csflow_a_owner")
                cursor.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
        plain = SCRATCH / "restore.temporary.dump"
        try:
            plain.write_bytes(crypt((WORK / final["file"]).read_bytes(), decrypt=True))
            check(
                hashlib.sha256(plain.read_bytes()).hexdigest() == final["plaintext_sha256"],
                "RESTORE_ARCHIVE_HASH_MISMATCH",
            )
            pg_tool(
                "pg_restore",
                [
                    "--single-transaction",
                    "--exit-on-error",
                    "--no-owner",
                    "--dbname",
                    "backend_a",
                    str(plain),
                ],
                target=True,
            )
        finally:
            plain.unlink(missing_ok=True)
        with engine(target=True, database="postgres") as db, db.begin() as connection:
            connection.execute(text("ALTER DATABASE backend_a RESET default_transaction_read_only"))
            connection.execute(text("GRANT CONNECT ON DATABASE backend_a TO PUBLIC,csflow_a_api"))
        with engine(target=True) as db, db.begin() as connection:
            check(
                schema_owner in {"pg_database_owner", "csflow_a_owner", "azure_pg_admin"},
                "UNREVIEWED_SCHEMA_OWNER",
            )
            connection.execute(text('ALTER SCHEMA public OWNER TO "' + schema_owner + '"'))
        with engine(target=True) as db, db.connect() as connection:
            target = fingerprint(connection)
            if source != target:
                save(
                    "copy-differences.json",
                    {
                        "table_sections_match": source["tables"] == target["tables"],
                        "catalog_sections_match": {
                            k: source["catalogs"][k] == v for k, v in target["catalogs"].items()
                        },
                        "sequences_match": source["sequences"] == target["sequences"],
                        "control_match": source["automation_control"] == target["automation_control"],
                    },
                )
            check(source == target, "MIGRATION_FINGERPRINT_MISMATCH")
        with engine() as db, db.connect() as connection:
            check(fingerprint(connection) == source, "OLD_DATABASE_CHANGED_AFTER_FENCE")
        save(
            "copy-verified.json",
            {
                "result": "PASS",
                "source_equals_target": True,
                "all_table_counts_and_hashes": True,
                "owners_privileges_constraints_indexes_triggers_functions_sequences": True,
                "tables": source["tables"],
                "sequences": source["sequences"],
                "catalogs": source["catalogs"],
                "migration": source["migration"],
                "automation_control_preserved": True,
                "seed_or_migration_executed": False,
                "target_app_not_started_yet": True,
            },
        )
        print("Final frozen dump restored; every table, sequence and catalog fingerprint matches", flush=True)
    except Exception:
        if frozen:
            # No public target app exists yet, so rollback cannot discard target customer writes.
            rollback_before_target_writes()
        raise
    finally:
        close_access()
        close_access(target=True)


def rollback_before_target_writes():
    check(
        not (WORK / "target-write-validation-started.json").exists(),
        "TARGET_WRITES_EXIST_RECONCILIATION_REQUIRED",
    )
    with engine(database="postgres") as db, db.begin() as connection:
        connection.execute(text("ALTER DATABASE backend_a RESET default_transaction_read_only"))
        connection.execute(text("ALTER ROLE csflow_a_api LOGIN"))
        connection.execute(text("GRANT CONNECT ON DATABASE backend_a TO PUBLIC,csflow_a_api"))
    cloud.az("webapp", "start", "-g", cloud.GROUP, "-n", OLD_APP, "--subscription", cloud.SUBSCRIPTION)
    save(
        "rollback.json",
        {"old_app_restarted": True, "target_writes_existed": False, "old_data_not_overwritten": True},
    )


def original_archive():
    archive = OLD_STATE / "backend-a.zip"
    manifest = json.loads((OLD_STATE / "artifact-manifest.json").read_text())
    check(
        hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["package_sha256"],
        "DEPLOYED_SOURCE_ARCHIVE_HASH_MISMATCH",
    )
    with zipfile.ZipFile(archive) as zip:
        check(
            {n: hashlib.sha256(zip.read(n)).hexdigest() for n in zip.namelist()} == manifest["files"],
            "ARTIFACT_FILES_MISMATCH",
        )
    return archive, manifest


def prebuild():
    check(
        not (WORK / "target-write-validation-started.json").exists(),
        "PREBUILD_NOT_ALLOWED_AFTER_PUBLIC_TARGET_WRITES",
    )
    archive, manifest = original_archive()
    cloud.az(
        "webapp",
        "deploy",
        "-g",
        cloud.GROUP,
        "-n",
        NEW_APP,
        "--src-path",
        str(archive),
        "--type",
        "zip",
        "--clean",
        "true",
        "--async",
        "true",
        "--track-status",
        "false",
        "--timeout",
        "1200000",
        "--subscription",
        cloud.SUBSCRIPTION,
    )
    token = cloud.az("account", "get-access-token", "--subscription", cloud.SUBSCRIPTION)["accessToken"]
    with httpx.Client(headers={"Authorization": "Bearer " + token}, timeout=60, trust_env=False) as client:
        for _ in range(90):
            response = client.get("https://" + NEW_APP + ".scm.azurewebsites.net/api/deployments/latest")
            if response.status_code in {200, 202}:
                result = response.json()
                if result.get("status") == 4 and result.get("complete"):
                    break
                check(result.get("status") != 3, "TARGET_BUILD_FAILED")
            time.sleep(10)
        else:
            raise RuntimeError("TARGET_BUILD_TIMEOUT")
    cloud.az("webapp", "stop", "-g", cloud.GROUP, "-n", NEW_APP, "--subscription", cloud.SUBSCRIPTION)
    check(
        cloud.rest(WORK, "get", resource("app", target=True), "2024-11-01")["properties"]["state"]
        == "Stopped",
        "TARGET_PREBUILD_NOT_STOPPED",
    )
    save(
        "target-prebuilt.json",
        {
            "exact_original_zip": True,
            "sha256": manifest["package_sha256"],
            "version": "0.6.1",
            "deployment_id": result["id"],
            "build_complete": True,
            "target_stopped_before_copy": True,
        },
    )
    print("Original ZIP built in target Linux runtime; target stopped until final DB copy", flush=True)


def deploy():
    check((WORK / "copy-verified.json").exists(), "COPY_VERIFICATION_REQUIRED")
    check((WORK / "target-prebuilt.json").exists(), "TARGET_PREBUILD_REQUIRED")
    _, manifest = original_archive()
    save(
        "target-write-validation-started.json",
        {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "old_database_remains_fenced": True,
            "never_blindly_fail_back_after_this_point": True,
        },
    )
    cloud.az("webapp", "start", "-g", cloud.GROUP, "-n", NEW_APP, "--subscription", cloud.SUBSCRIPTION)
    save(
        "target-deployed.json",
        {"exact_original_zip": True, "sha256": manifest["package_sha256"], "version": "0.6.1"},
    )
    print("Prebuilt target started after verified copy; old database remains fenced", flush=True)


def verify_old_rows(connection, expected):
    results = {}
    for table, record in expected.items():
        schema, name = table.split(".", 1)

        def quote(value):
            return '"' + value.replace('"', '""') + '"'

        identifier = quote(schema) + "." + quote(name)
        keys = ",".join("t." + quote(c) for c in record["pk"])
        result = connection.execute(
            text(f"""WITH expected AS (
           SELECT value->0 AS key,value->>1 AS hash FROM jsonb_array_elements(CAST(:rows AS jsonb)))
           SELECT count(*),count(*) FILTER (WHERE md5(row_to_json(t)::text)=e.hash)
           FROM {identifier} t JOIN expected e ON jsonb_build_array({keys})=e.key"""),
            {"rows": json.dumps(record["rows"])},
        ).one()
        check(result[0] == result[1] == len(record["rows"]), "OLD_ROW_MISSING_OR_CHANGED_" + table)
        results[table] = result[0]
    return results


def verify():
    check((WORK / "target-deployed.json").exists(), "TARGET_DEPLOYMENT_REQUIRED")
    with httpx.Client(timeout=30, trust_env=False) as client:
        for _ in range(90):
            try:
                if client.get("https://" + NEW_APP + ".azurewebsites.net/health/ready").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(5)
        else:
            raise RuntimeError("TARGET_READINESS_TIMEOUT")
    open_access()
    try:
        with engine() as db, db.connect() as connection:
            check(
                fingerprint(connection) == load("frozen-source-fingerprint.json"),
                "SOURCE_CHANGED_AFTER_CUTOVER",
            )
            check(
                connection.scalar(text("SELECT rolcanlogin FROM pg_roles WHERE rolname='csflow_a_api'"))
                is False,
                "OLD_RUNTIME_NOT_FENCED",
            )
            check(
                connection.scalar(text("SHOW default_transaction_read_only")) == "on",
                "OLD_DATABASE_NOT_READ_ONLY",
            )
    finally:
        close_access()
    fixture_backup = load("existing-fixture-backup.json")
    fixture_ids = json.loads(crypt((WORK / fixture_backup["file"]).read_bytes(), decrypt=True))
    values = cloud.state(NEW_STATE)
    assertions = []
    requests = 0
    with httpx.Client(
        base_url="https://" + NEW_APP + ".azurewebsites.net", timeout=30, trust_env=False
    ) as client:

        def request(method, path, status=200, **kwargs):
            nonlocal requests
            result = client.request(method, path, **kwargs)
            requests += 1
            check(result.status_code == status, "EXISTING_STATE_HTTP_STATUS_MISMATCH")
            return result

        identities = {}
        for label, role in [
            ("customer1", "CUSTOMER"),
            ("customer2", "CUSTOMER"),
            ("agent", "AGENT"),
            ("admin", "ADMIN"),
        ]:
            response = request(
                "POST",
                "/api/v1/auth/login",
                json={
                    "login_name": f"demo-{label}@csflow.example.test",
                    "password": values["accounts"][label],
                },
            )
            identities[label] = {"Authorization": "Bearer " + response.json()["access_token"]}
            check(
                request("GET", "/api/v1/auth/me", headers=identities[label]).json()["role"] == role,
                "EXISTING_ROLE_CHANGED",
            )
        assertions.append("four_existing_accounts_and_roles_preserved")
        tid = fixture_ids["ticket"]
        check(bool(tid), "NO_EXISTING_CUSTOMER_TICKET")
        detail = request("GET", "/api/v1/tickets/" + tid, headers=identities["customer1"]).json()
        check(detail["ticket_id"] == tid, "EXISTING_TICKET_NOT_RETURNED")
        request("GET", "/api/v1/tickets/" + tid + "/messages", headers=identities["customer1"])
        request("GET", "/api/v1/tickets/" + tid, 404, headers=identities["customer2"])
        assertions.append("existing_ticket_messages_and_cross_customer_denial")
        if fixture_ids["active_ticket"]:
            request("GET", "/api/v1/tickets/" + fixture_ids["active_ticket"], headers=identities["agent"])
            request("GET", "/api/v1/tickets/" + fixture_ids["active_ticket"], headers=identities["admin"])
            assertions.append("existing_active_assignment_and_admin_team_scope")
        if fixture_ids["resolved_ticket"]:
            request(
                "GET", "/api/v1/tickets/" + fixture_ids["resolved_ticket"], 404, headers=identities["agent"]
            )
            assertions.append("existing_resolved_ticket_does_not_revive_agent_access")
        if fixture_ids["followup"]:
            result = request(
                "GET", "/api/v1/followups/" + fixture_ids["followup"], headers=identities["customer1"]
            )
            check("internal_note" not in result.json(), "EXISTING_INTERNAL_NOTE_EXPOSED")
            request("GET", "/api/v1/staff/followups/" + fixture_ids["followup"], headers=identities["admin"])
            assertions.append("existing_followup_public_and_staff_boundary")
    save(
        "existing-state-http.json",
        {"result": "PASS", "asserted_http_requests": requests, "checks": assertions},
    )
    # The acceptance tool imports the target constants in this process only.
    # It uses fixed test writers exclusively for newly created synthetic tickets.
    with target_config():
        from scripts import azure_verify

        azure_verify.verify(NEW_STATE)
    open_access(target=True)
    try:
        row_backup = load("baseline-row-backup.json")
        expected = json.loads(crypt((WORK / row_backup["file"]).read_bytes(), decrypt=True))
        with engine(target=True) as db, db.connect() as connection:
            preserved = verify_old_rows(connection, expected)
            after = fingerprint(connection)
            check(
                after["migration"] == "0006"
                and after["automation_control"]
                == load("frozen-source-fingerprint.json")["automation_control"],
                "CONTROL_OR_MIGRATION_NOT_PRESERVED",
            )
        source = load("frozen-source-fingerprint.json")
        delta = {
            name: after["tables"][name]["count"] - table["count"]
            for name, table in source["tables"].items()
            if after["tables"][name]["count"] != table["count"]
        }
        snapshot = dump("target-post-verification", target=True)
        private_backup(
            "target-appsettings.private.json.dpapi",
            json.dumps(
                cloud.rest(
                    WORK, "post", resource("app", target=True) + "/config/appsettings/list", "2024-11-01"
                )
            ).encode(),
        )
        save("target-post-verification-backup.json", snapshot)
        report = {
            "result": "PASS",
            "all_original_rows_preserved": True,
            "original_rows_by_table": preserved,
            "test_insert_deltas": delta,
            "original_tables": len(preserved),
            "migration": "0006",
            "automation_pause_revision_generation_preserved": True,
            "old_database_still_fenced": True,
            "recovery_dump_restored_and_fingerprints_verified": True,
            "new_data_backup_after_verification": True,
            "https_report": "../azure-backend-a/https-verification.json",
            "no_seed_or_application_migrations": True,
        }
        save("migration-verification.json", report)
        print(json.dumps(report), flush=True)
    finally:
        close_access(target=True)


def blocking_locks(locks, ids):
    result = []
    for lock in locks:
        scope = lock["id"].lower().rsplit("/providers/microsoft.authorization/locks/", 1)[0]
        if lock["level"] in {"CanNotDelete", "ReadOnly"} and any(
            value.lower() == scope or value.lower().startswith(scope + "/") for value in ids
        ):
            result.append(lock)
    return result


def cleanup():
    check(load("migration-verification.json")["result"] == "PASS", "MIGRATION_ACCEPTANCE_REQUIRED")
    check(
        json.loads((NEW_STATE / "https-verification.json").read_text())["result"] == "PASS",
        "HTTPS_ACCEPTANCE_REQUIRED",
    )
    for filename in ("final-backup.json", "target-post-verification-backup.json"):
        record = load(filename)
        data = crypt((WORK / record["file"]).read_bytes(), decrypt=True)
        check(hashlib.sha256(data).hexdigest() == record["plaintext_sha256"], "RECOVERY_BACKUP_HASH_MISMATCH")
    with httpx.Client(timeout=30, trust_env=False) as client:
        check(
            client.get("https://" + NEW_APP + ".azurewebsites.net/health/ready").status_code == 200,
            "NEW_APP_NOT_READY_NO_DELETE",
        )
    new = cloud.owned(cloud.rest(WORK, "get", resource("app", target=True), "2024-11-01"))
    check(
        new["properties"]["serverFarmId"].lower() == resource("plan", target=True).lower(),
        "NEW_APP_DEPENDS_ON_OLD_PLAN",
    )
    before, already_absent = {}, []
    for kind in ("app", "postgres", "plan"):
        try:
            before[kind] = cloud.owned(
                cloud.rest(WORK, "get", resource(kind), "2024-08-01" if kind == "postgres" else "2024-11-01")
            )
        except RuntimeError as error:
            if str(error) not in {"ResourceNotFound", "NotFound"}:
                raise
            already_absent.append(resource(kind))
    if "app" in before:
        check(before["app"]["properties"]["state"] == "Stopped", "OLD_APP_MUST_REMAIN_STOPPED")
    check(
        all(
            before[k]["id"].lower() == resource(k).lower()
            and before[k]["tags"].get("component") == "backend-a"
            for k in before
        ),
        "EXACT_OLD_RESOURCE_ID_OR_COMPONENT_MISMATCH",
    )
    sites = (
        cloud.rest(WORK, "get", resource("plan") + "/sites", "2024-11-01")["value"]
        if "plan" in before
        else []
    )
    check(
        all(s["id"].lower() == resource("app").lower() for s in sites), "OTHER_APP_IN_OLD_PLAN_DO_NOT_DELETE"
    )
    databases = (
        cloud.rest(WORK, "get", resource("postgres") + "/databases", "2024-08-01")["value"]
        if "postgres" in before
        else []
    )
    check(
        {d["name"] for d in databases} <= {"backend_a", "postgres", "azure_sys", "azure_maintenance"},
        "UNREVIEWED_DATABASE_ON_OLD_SERVER",
    )
    locks = cloud.az("lock", "list", "-g", cloud.GROUP, "--subscription", cloud.SUBSCRIPTION)
    preflight = {
        "exact_old_ids": {k: resource(k) for k in ("app", "postgres", "plan")},
        "already_absent": already_absent,
        "old_plan_has_no_other_apps": True,
        "old_server_has_no_other_application_database": True,
        "backup_decryption_verified": True,
        "new_ready": True,
        "locks": [{"id": lock["id"], "level": lock["level"]} for lock in locks],
    }
    save("cleanup-preflight.json", preflight)
    if blocking_locks(locks, [resource(k) for k in before]):
        save("cleanup-result.json", {"status": "BLOCKED_BY_SHARED_TEAM_LOCK", "deleted": [], **preflight})
        print("Retirement is ready but blocked by shared team lock; no shared lock changed", flush=True)
        return
    deleted = list(already_absent)
    for kind in ("app", "postgres", "plan"):
        if kind not in before:
            continue
        if kind == "plan":
            try:
                cloud.rest(WORK, "get", resource("plan"), "2024-11-01")
            except RuntimeError as error:
                if str(error) not in {"ResourceNotFound", "NotFound"}:
                    raise
                # Azure may remove an empty plan with its final web app.
                deleted.append(resource(kind))
                save(
                    "cleanup-result.json",
                    {
                        "status": "DELETING",
                        "deleted": deleted,
                        "plan_already_absent_after_last_app": True,
                        **preflight,
                    },
                )
                continue
            check(
                not cloud.rest(WORK, "get", resource("plan") + "/sites", "2024-11-01")["value"],
                "OLD_PLAN_HAS_APPS_DO_NOT_DELETE",
            )
        try:
            cloud.rest(WORK, "delete", resource(kind), "2024-08-01" if kind == "postgres" else "2024-11-01")
        except RuntimeError as error:
            save(
                "cleanup-result.json",
                {"status": "DELETE_BLOCKED", "deleted": deleted, "blocking_code": str(error), **preflight},
            )
            raise
        deleted.append(resource(kind))
        save("cleanup-result.json", {"status": "DELETING", "deleted": deleted, **preflight})
    for kind in ("app", "postgres", "plan"):
        try:
            cloud.rest(WORK, "get", resource(kind), "2024-08-01" if kind == "postgres" else "2024-11-01")
        except RuntimeError as error:
            check(str(error) in {"ResourceNotFound", "NotFound"}, "OLD_RESOURCE_ABSENCE_NOT_CONFIRMED")
        else:
            raise RuntimeError("OLD_RESOURCE_STILL_EXISTS")
    with httpx.Client(timeout=30, trust_env=False) as client:
        health = {
            p: client.get("https://" + NEW_APP + ".azurewebsites.net" + p).status_code
            for p in ("/health/live", "/health/ready")
        }
    check(set(health.values()) == {200}, "NEW_HEALTH_AFTER_DELETE_FAILED")
    save(
        "cleanup-result.json",
        {
            "status": "PASS",
            "deleted": deleted,
            "old_resources_absent": True,
            "new_health": health,
            **preflight,
        },
    )
    print("All three exact old resources deleted; target live/ready still200", flush=True)


def retire_with_approved_lock_window():
    """Only after the user's explicit shared-lock exception approval.

    Default cleanup never changes locks. Restore the exact original protection
    in finally, even if one of the three old deletions fails.
    """
    check(load("migration-verification.json")["result"] == "PASS", "MIGRATION_ACCEPTANCE_REQUIRED")
    lock_id = f"/subscriptions/{cloud.SUBSCRIPTION}/resourceGroups/{cloud.GROUP}/providers/Microsoft.Authorization/locks/DO_NOT_DELETE"
    original = cloud.rest(WORK, "get", lock_id, "2016-09-01")
    check(
        original["id"].lower() == lock_id.lower() and original["properties"]["level"] == "CanNotDelete",
        "EXACT_ORIGINAL_SHARED_LOCK_REQUIRED",
    )
    save("original-team-lock.json", original)
    all_before = cloud.az("resource", "list", "-g", cloud.GROUP, "--subscription", cloud.SUBSCRIPTION)
    old_ids = [resource(k).lower() for k in ("app", "postgres", "plan")]
    protected_other_ids = {
        r["id"].lower()
        for r in all_before
        if not any(r["id"].lower() == old or r["id"].lower().startswith(old + "/") for old in old_ids)
    }
    started = datetime.now(timezone.utc).isoformat()
    unlocked = False
    try:
        unlocked = True
        cloud.rest(WORK, "delete", lock_id, "2016-09-01")
        save(
            "lock-window.json",
            {"user_explicitly_approved": True, "lock_id": lock_id, "started_at": started, "restored": False},
        )
        print(
            "Explicitly approved shared-lock window opened; deleting only the three exact old A resources",
            flush=True,
        )
        cleanup()
    finally:
        if unlocked:
            restored = False
            for attempt in range(5):
                try:
                    cloud.rest(WORK, "put", lock_id, "2016-09-01", {"properties": original["properties"]})
                    current = cloud.rest(WORK, "get", lock_id, "2016-09-01")
                    check(
                        current["properties"] == original["properties"], "TEAM_LOCK_PROPERTIES_NOT_RESTORED"
                    )
                    restored = True
                    break
                except Exception:
                    if attempt == 4:
                        raise
                    time.sleep(2)
            save(
                "lock-window.json",
                {
                    "user_explicitly_approved": True,
                    "lock_id": lock_id,
                    "started_at": started,
                    "restored": restored,
                    "restored_at": datetime.now(timezone.utc).isoformat(),
                    "same_name_level_notes_owners": True,
                    "shared_resources_not_modified": True,
                },
            )
            print("Original DO_NOT_DELETE CanNotDelete lock restored with identical properties", flush=True)
    after = cloud.az("resource", "list", "-g", cloud.GROUP, "--subscription", cloud.SUBSCRIPTION)
    check(
        protected_other_ids <= {r["id"].lower() for r in after}, "PREEXISTING_OTHER_RESOURCE_ABSENCE_DETECTED"
    )
    save(
        "other-resources-preserved.json",
        {"result": "PASS", "preexisting_nonretired_resource_ids_preserved": len(protected_other_ids)},
    )


def main():
    global PG_BIN, SCRATCH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "backup",
            "provision",
            "prebuild",
            "copy",
            "deploy",
            "verify",
            "cleanup",
            "retire-with-lock-window",
        ],
    )
    parser.add_argument("--pg-bin", type=Path)
    parser.add_argument(
        "--allow-shared-lock-window",
        action="store_true",
        help="Requires separate explicit user approval; never inferred from resource delete approval",
    )
    args = parser.parse_args()
    if args.command == "retire-with-lock-window":
        check(args.allow_shared_lock_window, "EXPLICIT_SHARED_LOCK_WINDOW_APPROVAL_REQUIRED")
    PG_BIN = args.pg_bin
    cloud.private_directory(WORK)
    SCRATCH = Path(tempfile.mkdtemp(prefix="csflow-a-migration-"))
    cloud.private_directory(SCRATCH)
    try:
        {
            "backup": backup,
            "provision": provision,
            "prebuild": prebuild,
            "copy": freeze_copy,
            "deploy": deploy,
            "verify": verify,
            "cleanup": cleanup,
            "retire-with-lock-window": retire_with_approved_lock_window,
        }[args.command]()
    finally:
        if not list(SCRATCH.iterdir()):
            SCRATCH.rmdir()


if __name__ == "__main__":
    main()
