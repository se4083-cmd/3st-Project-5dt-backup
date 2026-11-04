"""Release an exact commit to existing A resources only. No provision/seed/configure.

Explicit invocation required. Secrets stay in existing private state/memory.
No tests run on Azure DB; no shared locks, other workers or resource plans change.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import subprocess
import zipfile
from contextlib import contextmanager
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from scripts import azure_deploy as cloud
from scripts.azure_migrate import crypt

STATE = cloud.ROOT / ".cache/azure-backend-a"
WORK = cloud.ROOT / ".cache/azure-release-0110"
RULE_NAME = "backend-a-release-0110-temporary"
EXPECTED_VERSION = "0.11.0"
EXPECTED_HEAD = "0011"


def save(name, value):
    cloud.private_directory(WORK)
    (WORK / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def package(directory, sha, *, recovery=False):
    """Pure local Git-byte package. Recovery uses reviewed 0.10 + head0011 patch."""
    prefix = "backend/backend-a/"
    repo_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=cloud.ROOT, text=True
    ).strip()
    entries = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", sha, "--", prefix], cwd=repo_root, text=True
    ).splitlines()
    paths = [
        p
        for p in entries
        if (
            p.startswith((prefix + "app/", prefix + "migrations/"))
            and p.endswith(".py")
            or p in [prefix + x for x in ("requirements.txt", "pyproject.toml", "alembic.ini", "startup.sh")]
        )
    ]
    if not paths:
        raise RuntimeError("PACKAGE_SOURCE_NOT_FOUND")
    directory.mkdir(parents=True, exist_ok=True)
    name = "recovery.zip" if recovery else "release.zip"
    hashes = {}
    with zipfile.ZipFile(directory / name, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(paths):
            raw = subprocess.check_output(["git", "show", sha + ":" + path], cwd=cloud.ROOT)
            rel = path[len(prefix) :]
            if recovery and rel == "app/main.py":
                assert raw.count(b'!= "0010"') == 1 and raw.count(b'version="0.10.0"') == 1
                raw = raw.replace(b'!= "0010"', b'!= "0011"').replace(
                    b'version="0.10.0"', b'version="0.10.0+recovery0011"'
                )
            hashes[rel] = hashlib.sha256(raw).hexdigest()
            z.writestr(rel, raw)
    manifest = dict(
        source_sha=sha,
        recovery_patch="readiness0011/version only" if recovery else None,
        package_sha256=hashlib.sha256((directory / name).read_bytes()).hexdigest(),
        files=hashes,
    )
    (directory / (name + ".manifest.json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


@contextmanager
def database():
    """Open one exact operator IP rule temporarily; never alter an existing rule."""
    pg = cloud.BASE + f"Microsoft.DBforPostgreSQL/flexibleServers/{cloud.PG}"
    cloud.owned(cloud.rest(STATE, "get", pg, "2024-08-01"))
    existing = cloud.rest(STATE, "get", pg + "/firewallRules", "2024-08-01")["value"]
    if any(x["name"] == RULE_NAME for x in existing):
        raise RuntimeError("TEMPORARY_RULE_ALREADY_EXISTS_NO_OVERWRITE")
    with httpx.Client(trust_env=False, timeout=20) as client:
        a = str(ipaddress.IPv4Address(client.get("https://api.ipify.org").text.strip()))
        b = str(ipaddress.IPv4Address(client.get("https://checkip.amazonaws.com").text.strip()))
    if a != b:
        raise RuntimeError("OPERATOR_EGRESS_INCONSISTENT")
    engine = None
    try:
        cloud.rest(
            STATE,
            "put",
            pg + "/firewallRules/" + RULE_NAME,
            "2024-08-01",
            {"properties": {"startIpAddress": a, "endIpAddress": a}},
        )
        values = cloud.state(STATE)
        url = make_url(cloud.database_url(values, local=True)).update_query_dict(
            {
                "application_name": "backend-a-release",
                "options": "-c lock_timeout=5000 -c statement_timeout=120000",
            }
        )
        engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 15})
        yield engine, url, values
    finally:
        if engine:
            engine.dispose()
        try:
            cloud.rest(STATE, "delete", pg + "/firewallRules/" + RULE_NAME, "2024-08-01")
            result = "REMOVED"
        except RuntimeError as error:
            if str(error) != "ScopeLocked":
                raise
            cloud.rest(
                STATE,
                "put",
                pg + "/firewallRules/" + RULE_NAME,
                "2024-08-01",
                {"properties": {"startIpAddress": "127.0.0.1", "endIpAddress": "127.0.0.1"}},
            )
            result = "DISABLED_LOOPBACK_SHARED_LOCK_PRESERVED"
        print("Own temporary firewall: " + result, flush=True)


def inspect():
    account = cloud.az("account", "show", "--subscription", cloud.SUBSCRIPTION)
    assert account["id"] == cloud.SUBSCRIPTION
    resources = []
    for provider, name, api in [
        ("Microsoft.Web/sites", cloud.APP, "2024-11-01"),
        ("Microsoft.Web/serverfarms", cloud.PLAN, "2024-11-01"),
        ("Microsoft.DBforPostgreSQL/flexibleServers", cloud.PG, "2024-08-01"),
    ]:
        r = cloud.owned(cloud.rest(STATE, "get", cloud.BASE + provider + "/" + name, api))
        resources.append(
            dict(
                name=name,
                region=r["location"],
                sku=r.get("sku"),
                backup=r.get("properties", {}).get("backup"),
            )
        )
    settings = {
        r["name"]: r["value"]
        for r in cloud.az(
            "webapp",
            "config",
            "appsettings",
            "list",
            "-g",
            cloud.GROUP,
            "-n",
            cloud.APP,
            "--subscription",
            cloud.SUBSCRIPTION,
        )
    }
    runtime = make_url(settings["DATABASE_URL"])
    assert (
        runtime.host == cloud.PG + ".postgres.database.azure.com"
        and runtime.database == cloud.DATABASE
        and runtime.username == "csflow_a_api"
    )
    assert settings.get("APP_ENV") == "production" and settings.get("ENABLE_DEV_SEED") == "false"
    result = dict(
        resources=resources,
        cors_origins=json.loads(settings.get("CORS_ORIGINS", "[]")),
        service_subject_count=len(json.loads(settings.get("ANALYTICS_SERVICE_IDS", "[]"))),
        runtime_role_confirmed=True,
    )
    cloud.private_directory(WORK)
    (WORK / "appsettings-before.dpapi").write_bytes(crypt(json.dumps(settings).encode()))
    with database() as (engine, _, __), engine.connect() as c:
        result.update(
            db_head=c.scalar(text("SELECT version_num FROM alembic_version")),
            paused=c.scalar(text("SELECT paused FROM automation_control WHERE singleton_id=1")),
            active_other_sessions=c.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state<>'idle'"
                )
            ),
            login_roles=[
                dict(r)
                for r in c.execute(
                    text(
                        "SELECT rolname,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolcanlogin AND rolname NOT LIKE 'pg_%' AND rolname NOT LIKE 'azure_%'"
                    )
                ).mappings()
            ],
        )
    # Role names/settings remain private, only aggregates are suitable for evidence.
    save("inspection-private.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "login_roles"}, default=str), flush=True)
    return result


def backup(engine, url, pg_bin):
    """Native custom dump in memory, encrypted immediately; validate its TOC."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PG")}
    env.update(
        PGHOST=url.host,
        PGPORT=str(url.port or 5432),
        PGDATABASE=url.database,
        PGUSER=url.username,
        PGPASSWORD=url.password,
        PGSSLMODE="verify-full",
        PGSSLROOTCERT=url.query["sslrootcert"],
    )
    raw = subprocess.run(
        [str(pg_bin / "pg_dump.exe"), "--format=custom", "--no-owner"], env=env, capture_output=True
    )
    if raw.returncode:
        raise RuntimeError("PG_DUMP_FAILED_NO_DIAGNOSTIC_DISCLOSURE")
    toc = subprocess.run([str(pg_bin / "pg_restore.exe"), "--list"], input=raw.stdout, capture_output=True)
    if toc.returncode:
        raise RuntimeError("BACKUP_TOC_INVALID")
    encrypted = crypt(raw.stdout)
    assert crypt(encrypted, decrypt=True) == raw.stdout
    path = WORK / "pre-release.dump.dpapi"
    if path.exists():
        raise RuntimeError("BACKUP_EXISTS_NO_OVERWRITE")
    path.write_bytes(encrypted)
    record = dict(
        format="PG_CUSTOM",
        encrypted="WINDOWS_CURRENT_USER_DPAPI",
        bytes=len(encrypted),
        sha256=hashlib.sha256(encrypted).hexdigest(),
        toc_sha256=hashlib.sha256(toc.stdout).hexdigest(),
        decrypt_roundtrip=True,
    )
    save("backup-summary.json", record)
    return record


def fingerprint(connection, tables):
    result = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        row = connection.execute(
            text(
                "SELECT count(*), md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY md5(row_to_json(t)::text)), '')) FROM "
                + quoted
                + " t"
            )
        ).one()
        result[table] = dict(count=row[0], rowset_md5=row[1])
    return result


def migrate(pg_bin):
    """Existing app can run; additive DDL bounded by lock_timeout. No seed."""
    with database() as (engine, url, values):
        with engine.connect() as c:
            assert c.scalar(text("SELECT current_database()")) == cloud.DATABASE
            assert c.scalar(text("SELECT paused FROM automation_control WHERE singleton_id=1")) is True
            before = c.scalar(text("SELECT version_num FROM alembic_version"))
            active = c.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state<>'idle'"
                )
            )
            if active:
                raise RuntimeError("ACTIVE_SHARED_WRITER_COORDINATION_REQUIRED")
            tables = (
                c.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version' ORDER BY tablename"
                    )
                )
                .scalars()
                .all()
            )
            counts = fingerprint(c, tables)
        if before != "0006":
            raise RuntimeError("REVIEW_NEW_DEPLOYMENT_DB_HEAD_BEFORE_MIGRATION")
        backup(engine, url, pg_bin)
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"CSFLOW_LOCAL_ONLY", "CSFLOW_FIXTURE_DIR", "TEST_POSTGRES_URL"}
        }
        env.update(
            APP_ENV="production",
            DATABASE_URL=url.render_as_string(hide_password=False),
            JWT_SECRET=values["jwt"],
            ENABLE_DEV_SEED="false",
            CSFLOW_ENV_FILE=str(WORK / "no-env-file"),
        )
        result = subprocess.run(
            [os.sys.executable, "-m", "alembic", "upgrade", EXPECTED_HEAD],
            cwd=cloud.ROOT,
            env=env,
            capture_output=True,
        )
        if result.returncode:
            raise RuntimeError("ADDITIVE_MIGRATION_FAILED_TRANSACTION_ROLLED_BACK_REVIEW_REQUIRED")
        with engine.begin() as c:
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == EXPECTED_HEAD
            assert c.scalar(text("SELECT paused FROM automation_control WHERE singleton_id=1")) is True
            assert counts == fingerprint(c, tables), "EXISTING_ROWSET_CHANGED_REVIEW_REQUIRED"
            # Verified existing app DB identity only. No staff capability grants here.
            new_tables = (
                c.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
                )
                .scalars()
                .all()
            )
            for table in set(new_tables) - set(tables) - {"alembic_version"}:
                c.execute(text('GRANT SELECT,INSERT,UPDATE ON TABLE "' + table + '" TO csflow_a_api'))
        save(
            "migration-summary.json",
            dict(
                before=before,
                after=EXPECTED_HEAD,
                old_table_counts_preserved=counts,
                paused=True,
                seed_run=False,
                staff_grants_added=False,
                runtime_identity_new_table_DML=True,
                lock_timeout_ms=5000,
            ),
        )
        print(
            "Migration verified: "
            + before
            + " -> "
            + EXPECTED_HEAD
            + "; existing row counts/PAUSED preserved",
            flush=True,
        )


def deploy(sha, *, recovery=False):
    artifact = WORK / ("recovery.zip" if recovery else "release.zip")
    manifest = json.loads((WORK / (artifact.name + ".manifest.json")).read_text())
    assert (
        manifest["source_sha"] == sha
        and manifest["package_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    )
    if not (WORK / "migration-summary.json").exists() or not (WORK / "pre-release.dump.dpapi").exists():
        raise RuntimeError("VERIFIED_MIGRATION_AND_BACKUP_REQUIRED")
    assert json.loads((WORK / "migration-summary.json").read_text())["after"] == EXPECTED_HEAD
    cloud.owned(cloud.rest(STATE, "get", cloud.BASE + f"Microsoft.Web/sites/{cloud.APP}", "2024-11-01"))
    result = cloud.az(
        "webapp",
        "deploy",
        "-g",
        cloud.GROUP,
        "-n",
        cloud.APP,
        "--src-path",
        str(artifact),
        "--type",
        "zip",
        "--clean",
        "true",
        "--restart",
        "true",
        "--timeout",
        "1200000",
        "--subscription",
        cloud.SUBSCRIPTION,
    )
    save(
        "deployment-summary.json",
        dict(
            source_sha=sha,
            recovery=recovery,
            package_sha256=manifest["package_sha256"],
            deployment_result={
                k: result.get(k)
                for k in ("id", "status", "deploymentId", "status_text")
                if isinstance(result, dict) and k in result
            },
        ),
    )
    print("Exact package deployed: " + sha + (" recovery patch" if recovery else ""), flush=True)


def verify():
    paths = ["/health/live", "/health/ready", "/docs", "/openapi.json"]
    with httpx.Client(
        base_url="https://" + cloud.APP + ".azurewebsites.net", trust_env=False, timeout=30
    ) as client:
        status = {p: client.get(p).status_code for p in paths}
        assert all(v == 200 for v in status.values()), "HTTPS_NOT_READY"
        spec = client.get("/openapi.json").json()
        assert spec["info"]["version"] == EXPECTED_VERSION
        for path in [
            "/api/v1/staff/quality/automation-metrics",
            "/api/v1/staff/voc-improvements/{action_id}/effects",
            "/api/v1/analytics/voc-effects/batches",
            "/api/v1/staff/workload",
            "/api/v1/staff/assignment-recommendations",
        ]:
            assert path in spec["paths"]
        rejects = {}
        for path in [
            "/api/v1/staff/workload",
            "/api/v1/staff/assignment-recommendations",
            "/api/v1/staff/voc-improvements",
            "/api/v1/staff/quality/samples",
            "/api/v1/staff/quality/automation-metrics?response_start=2026-11-01T00:00:00Z&response_end=2026-11-05T00:00:00Z",
        ]:
            rejects[path] = client.get(path).status_code
        assert set(rejects.values()) == {401}
    with database() as (engine, _, __), engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == EXPECTED_HEAD
        assert c.scalar(text("SELECT paused FROM automation_control WHERE singleton_id=1")) is True
    after = {
        r["name"]: r["value"]
        for r in cloud.az(
            "webapp",
            "config",
            "appsettings",
            "list",
            "-g",
            cloud.GROUP,
            "-n",
            cloud.APP,
            "--subscription",
            cloud.SUBSCRIPTION,
        )
    }
    before = json.loads(crypt((WORK / "appsettings-before.dpapi").read_bytes(), decrypt=True))
    for key in [
        "DATABASE_URL",
        "JWT_SECRET",
        "ANALYTICS_SERVICE_IDS",
        "ANALYTICS_SERVICE_SECRET",
        "CORS_ORIGINS",
        "APP_ENV",
        "ENABLE_DEV_SEED",
    ]:
        assert after.get(key) == before.get(key), "EXISTING_SETTING_CHANGED"
    report = dict(
        version=EXPECTED_VERSION,
        db_head=EXPECTED_HEAD,
        https=status,
        unauthenticated=rejects,
        paused=True,
        existing_settings_preserved=True,
        actual_B_AI_Fabric_Frontend_verified=False,
        shared_db_test_suite_run=False,
    )
    save("https-summary.json", report)
    print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "package", "migrate", "deploy", "verify"])
    parser.add_argument("--sha")
    parser.add_argument("--recovery", action="store_true")
    parser.add_argument("--pg-bin", type=Path)
    args = parser.parse_args()
    cloud.private_directory(WORK)
    if args.command == "inspect":
        inspect()
    elif args.command == "package":
        package(WORK, args.sha, recovery=args.recovery)
    elif args.command == "migrate":
        if not args.pg_bin:
            raise RuntimeError("PG_BIN_REQUIRED")
        migrate(args.pg_bin)
    elif args.command == "deploy":
        deploy(args.sha, recovery=args.recovery)
    elif args.command == "verify":
        verify()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import re

        code = str(exc) if re.fullmatch(r"[A-Z][A-Z0-9_.:-]{0,127}", str(exc)) else type(exc).__name__
        print("RELEASE_STEP_FAILED: " + code, flush=True)
        raise SystemExit(1) from None
