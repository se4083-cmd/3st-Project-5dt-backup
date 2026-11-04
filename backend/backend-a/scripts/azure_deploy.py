"""Explicit, manual Azure team-dev deployment. Never imported by local startup.

Only dedicated Backend A resources in the reviewed resource group are permitted.
Secrets remain in a private ignored state directory and encrypted App Settings;
they are never printed, placed in the package, or passed as CLI arguments.
"""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SUBSCRIPTION = "27db5ec6-d206-4028-b5e1-6004dca5eeef"
GROUP = "5dt-final-team1"
REGION = "koreacentral"
# Active resources after the approved, verified migration. Old resource IDs are
# isolated in azure_migrate.py; this normal deploy tool never recreates them.
PLAN = "csflow-backend-a-plan"
APP = "csflow-backend-a"
PG = "csflow-backend-a-pg"
DATABASE = "backend_a"
BASE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/"
TAGS = {"project": "cs-flow-ai", "owner": "backend-a", "component": "backend-a", "environment": "team-dev"}


def az(*args):
    result = subprocess.run(
        [shutil.which("az") or "az", *args, "--only-show-errors", "-o", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "AZURE_CORE_COLLECT_TELEMETRY": "no"},
    )
    if result.returncode:
        # CLI can echo ARM bodies or connection strings on errors. Keep raw
        # diagnostics out of logs; a separate secret-free status is safe.
        import re

        codes = re.findall(r'"code"\s*:\s*"([A-Za-z0-9_.-]+)"|\(([A-Za-z0-9_.-]+)\)', result.stderr)
        code = next((a or b for a, b in codes), "AZURE_COMMAND_FAILED")
        raise RuntimeError(code)
    return json.loads(result.stdout) if result.stdout.strip() else None


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        user = (
            "*"
            + subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value",
                ],
                text=True,
            ).strip()
        )
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"],
            check=True,
            capture_output=True,
        )


def state(directory, *, create=False):
    private_directory(directory)
    path = directory / "secrets.json"
    if not path.exists():
        if not create:
            raise RuntimeError("DEPLOYMENT_SECRET_STATE_REQUIRED")
        values = {k: secrets.token_urlsafe(48) for k in ("db_admin", "db_runtime", "jwt", "service")}
        values["accounts"] = {
            k: secrets.token_urlsafe(30) for k in ("customer1", "customer2", "agent", "admin")
        }
        path.write_text(json.dumps(values), encoding="utf-8")
        path.chmod(0o600)
    return json.loads(path.read_text(encoding="utf-8"))


def rest(directory, method, resource, api, body=None):
    token = az("account", "get-access-token", "--subscription", SUBSCRIPTION)["accessToken"]
    url = f"https://management.azure.com{resource}?api-version={api}"
    with httpx.Client(headers={"Authorization": "Bearer " + token}, timeout=120, trust_env=False) as client:
        for attempt in range(4):
            response = client.request(method, url, json=body)
            if not response.is_error:
                break
            code = response.json().get("error", {}).get("code", "")
            if code not in {
                "ServerTimeout",
                "ServerIsBusy",
                "ServerBusyWithOtherOperation",
                "TooManyRequests",
                "AnotherOperationInProgress",
            }:
                break
            time.sleep(5 * (attempt + 1))
        if response.is_error:
            raise RuntimeError(response.json().get("error", {}).get("code", "ARM_REQUEST_FAILED"))
        async_status = response.headers.get("Azure-AsyncOperation")
        polling = async_status or response.headers.get("Location")
        if response.status_code == 202 and polling:
            if not polling.startswith("https://management.azure.com/"):
                raise RuntimeError("UNEXPECTED_ARM_POLLING_HOST")
            for _ in range(90):
                time.sleep(10)
                poll = client.get(polling)
                result = poll.json()
                status = result.get("status", "")
                if status == "Succeeded":
                    break
                if not async_status and poll.status_code == 200 and not status:
                    break  # Location can return the completed resource, not a status document.
                if poll.is_error or status in {"Failed", "Canceled"}:
                    raise RuntimeError(result.get("error", {}).get("code", "ARM_OPERATION_FAILED"))
            else:
                raise RuntimeError("ARM_OPERATION_TIMEOUT")
            response = client.get(url)
        return response.json() if response.content else None


def owned(resource):
    if (
        resource.get("tags", {}).get("owner") != "backend-a"
        or resource.get("location", "").replace(" ", "").lower() != REGION
    ):
        raise RuntimeError("RESOURCE_OWNERSHIP_OR_REGION_MISMATCH")
    return resource


def provision(directory):
    # Existing plan was explicitly created following the reviewed cost notice.
    owned(rest(directory, "get", BASE + f"Microsoft.Web/serverfarms/{PLAN}", "2024-11-01"))
    apps = az("webapp", "list", "-g", GROUP, "--subscription", SUBSCRIPTION)
    servers = az("postgres", "flexible-server", "list", "-g", GROUP, "--subscription", SUBSCRIPTION)
    existing = any(a["name"] == APP for a in apps) or any(s["name"] == PG for s in servers)
    values = state(directory, create=not existing)
    if not any(a["name"] == APP for a in apps):
        az(
            "webapp",
            "create",
            "-g",
            GROUP,
            "-n",
            APP,
            "--plan",
            PLAN,
            "--runtime",
            "PYTHON:3.13",
            "--https-only",
            "true",
            "--tags",
            *[f"{k}={v}" for k, v in TAGS.items()],
            "--subscription",
            SUBSCRIPTION,
        )
    owned(rest(directory, "get", BASE + f"Microsoft.Web/sites/{APP}", "2024-11-01"))
    print("Backend A HTTPS app created/ownership checked", flush=True)
    if not any(s["name"] == PG for s in servers):
        rest(
            directory,
            "put",
            BASE + f"Microsoft.DBforPostgreSQL/flexibleServers/{PG}",
            "2024-08-01",
            {
                "location": REGION,
                "tags": TAGS,
                "sku": {"name": "Standard_B1ms", "tier": "Burstable"},
                "properties": {
                    "version": "16",
                    "administratorLogin": "csflow_a_owner",
                    "administratorLoginPassword": values["db_admin"],
                    "storage": {"storageSizeGB": 32, "autoGrow": "Disabled"},
                    "backup": {"backupRetentionDays": 7, "geoRedundantBackup": "Disabled"},
                    "highAvailability": {"mode": "Disabled"},
                    "network": {"publicNetworkAccess": "Enabled"},
                    "authConfig": {"passwordAuth": "Enabled", "activeDirectoryAuth": "Disabled"},
                },
            },
        )
        print("Dedicated PostgreSQL creation submitted (no firewall rules)", flush=True)
    for _ in range(60):
        server = owned(
            rest(directory, "get", BASE + f"Microsoft.DBforPostgreSQL/flexibleServers/{PG}", "2024-08-01")
        )
        status = server["properties"]["state"]
        if status == "Ready":
            print("Dedicated PostgreSQL Ready", flush=True)
            return
        if status in {"Failed", "Disabled"}:
            raise RuntimeError("POSTGRES_PROVISIONING_" + status.upper())
        print("PostgreSQL provisioning: " + status, flush=True)
        time.sleep(20)
    raise RuntimeError("POSTGRES_PROVISIONING_TIMEOUT")


def package(directory):
    output = directory / "backend-a.zip"
    paths = []
    for folder in ("app", "migrations"):
        paths += [p for p in (ROOT / folder).rglob("*.py") if "__pycache__" not in p.parts]
    paths += [ROOT / p for p in ("requirements.txt", "pyproject.toml", "alembic.ini", "startup.sh")]
    paths += [ROOT / "scripts/__init__.py", ROOT / "scripts/azure_bootstrap.py"]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.writestr(path.relative_to(ROOT).as_posix(), path.read_bytes().replace(b"\r\n", b"\n"))
    manifest = {
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "worktree_changed": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "package_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "files": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for p in paths
        },
    }
    (directory / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        json.dumps(
            {"package_files": len(paths), "bytes": output.stat().st_size, "credentials_included": False}
        )
    )


def database_url(values, *, runtime=False, local=False):
    from sqlalchemy.engine import URL

    # Linux App Service image maintains the OS trusted certificate bundle.
    # Local administration uses certifi's maintained public CA bundle instead.
    if local:
        import certifi

        contents = Path(certifi.where()).read_bytes()
        # PUBLIC CA bundle, not a credential. Windows libpq needs an ASCII path.
        certificate = Path(tempfile.gettempdir()) / (
            "csflow-a-ca-" + hashlib.sha256(contents).hexdigest()[:12] + ".pem"
        )
        if not certificate.exists():
            certificate.write_bytes(contents)
        root = str(certificate)
    else:
        root = "/etc/ssl/certs/ca-certificates.crt"
    return URL.create(
        "postgresql+psycopg",
        username="csflow_a_api" if runtime else "csflow_a_owner",
        password=values["db_runtime" if runtime else "db_admin"],
        host=PG + ".postgres.database.azure.com",
        port=5432,
        database=DATABASE,
        query={"sslmode": "verify-full", "sslrootcert": root},
    ).render_as_string(hide_password=False)


def close_operator_firewall(directory, resource):
    prefix = BASE + f"Microsoft.DBforPostgreSQL/flexibleServers/{PG}/firewallRules/"
    if resource not in {
        prefix + "backend-a-bootstrap-temporary",
        prefix + "backend-a-verification-temporary",
    }:
        raise RuntimeError("ONLY_OWN_TEMPORARY_RULE_ALLOWED")
    try:
        rest(directory, "delete", resource, "2024-08-01")
        return "REMOVED"
    except RuntimeError as error:
        if str(error) != "ScopeLocked":
            raise
        # Preserve the shared team delete lock. Loopback is NOT Azure's special
        # 0.0.0.0 "allow all Azure services" rule and cannot admit this operator.
        rest(
            directory,
            "put",
            resource,
            "2024-08-01",
            {"properties": {"startIpAddress": "127.0.0.1", "endIpAddress": "127.0.0.1"}},
        )
        return "DISABLED_LOOPBACK_SHARED_DELETE_LOCK"


def configure(directory):
    values = state(directory)
    app_id = BASE + f"Microsoft.Web/sites/{APP}"
    app = owned(rest(directory, "get", app_id, "2024-11-01"))
    pg_id = BASE + f"Microsoft.DBforPostgreSQL/flexibleServers/{PG}"
    owned(rest(directory, "get", pg_id, "2024-08-01"))
    # No 0.0.0.0 "all Azure" or 0.0.0.0/0 Internet rule.
    ips = set(app["properties"]["outboundIpAddresses"].split(","))
    existing_rules = {
        r["name"]: r["properties"]
        for r in rest(directory, "get", pg_id + "/firewallRules", "2024-08-01")["value"]
    }
    for i, ip in enumerate(sorted(ips)):
        if existing_rules.get(f"backend-a-app-{i}") == {"startIpAddress": ip, "endIpAddress": ip}:
            continue
        rest(
            directory,
            "put",
            pg_id + f"/firewallRules/backend-a-app-{i}",
            "2024-08-01",
            {"properties": {"startIpAddress": ip, "endIpAddress": ip}},
        )
    databases = rest(directory, "get", pg_id + "/databases", "2024-08-01")["value"]
    if not any(d["name"] == DATABASE for d in databases):
        rest(
            directory,
            "put",
            pg_id + "/databases/" + DATABASE,
            "2024-08-01",
            {"properties": {"charset": "UTF8", "collation": "en_US.utf8"}},
        )
    for name, value in {
        "log_error_verbosity": "terse",
        "log_parameter_max_length": "0",
        "log_parameter_max_length_on_error": "0",
        "log_statement": "none",
    }.items():
        current = rest(directory, "get", pg_id + "/configurations/" + name, "2024-08-01")
        if current["properties"]["value"] == value:
            continue
        rest(
            directory,
            "put",
            pg_id + "/configurations/" + name,
            "2024-08-01",
            {"properties": {"value": value, "source": "user-override"}},
        )
    settings = {
        "APP_ENV": "production",
        "DATABASE_URL": database_url(values, runtime=True),
        "JWT_SECRET": values["jwt"],
        "ANALYTICS_SERVICE_SECRET": values["service"],
        "ANALYTICS_SERVICE_IDS": "[]",
        "ENABLE_DEV_SEED": "false",
        "CORS_ORIGINS": "[]",
        "ALLOWED_HOSTS": json.dumps([app["properties"]["defaultHostName"], "127.0.0.1", "localhost"]),
        "POOL_SIZE": "3",
        "MAX_OVERFLOW": "2",
        "POOL_TIMEOUT": "10",
        "WEB_CONCURRENCY": "1",
        "SCM_DO_BUILD_DURING_DEPLOYMENT": "true",
        "TOKEN_MINUTES": "30",
        "FORWARDED_ALLOW_IPS": "127.0.0.1",
        "DB_STATEMENT_TIMEOUT_MS": "10000",
    }
    rest(directory, "put", app_id + "/config/appsettings", "2024-11-01", {"properties": settings})
    rest(directory, "patch", app_id, "2024-11-01", {"properties": {"httpsOnly": True}})
    rest(
        directory,
        "put",
        app_id + "/config/web",
        "2024-11-01",
        {
            "properties": {
                "linuxFxVersion": "PYTHON|3.13",
                "appCommandLine": "sh startup.sh",
                "alwaysOn": True,
                "minTlsVersion": "1.2",
                "scmMinTlsVersion": "1.2",
                "ftpsState": "Disabled",
                "http20Enabled": True,
                "healthCheckPath": "/health/ready",
                "httpLoggingEnabled": False,
                "detailedErrorLoggingEnabled": False,
                "requestTracingEnabled": False,
            }
        },
    )
    for name in ("ftp", "scm"):
        rest(
            directory,
            "put",
            app_id + "/basicPublishingCredentialsPolicies/" + name,
            "2024-11-01",
            {"properties": {"allow": False}},
        )
    (directory / "resources.json").write_text(
        json.dumps(
            {
                "subscription": SUBSCRIPTION,
                "group": GROUP,
                "region": REGION,
                "app": APP,
                "plan": PLAN,
                "postgres": PG,
                "database": DATABASE,
                "api_url": "https://" + app["properties"]["defaultHostName"],
                "db_firewall_exact_ips": len(ips),
            },
            indent=2,
        )
    )
    print("A-only TLS settings, exact-IP firewall and encrypted App Settings configured", flush=True)


def bootstrap(directory):
    from alembic import command
    from alembic.config import Config
    from psycopg import sql
    from sqlalchemy import text

    from app.config import Settings, get_settings
    from app.db import build_engine, session_factory
    from scripts.azure_bootstrap import seed_cloud

    values = state(directory)
    pg_id = BASE + f"Microsoft.DBforPostgreSQL/flexibleServers/{PG}"
    owned(rest(directory, "get", pg_id, "2024-08-01"))
    # Azure ARM observes the actual operator client address. No third-party IP service.
    events = az(
        "monitor",
        "activity-log",
        "list",
        "--resource-id",
        BASE + f"Microsoft.Web/sites/{APP}",
        "--offset",
        "1h",
        "--max-events",
        "100",
        "--subscription",
        SUBSCRIPTION,
    )
    ip = next(
        (
            (e.get("httpRequest") or {}).get("clientIpAddress")
            for e in events
            if (e.get("httpRequest") or {}).get("clientIpAddress")
        ),
        None,
    )
    if not ip:
        raise RuntimeError("OPERATOR_PUBLIC_IP_REQUIRED")
    import ipaddress

    ip = str(ipaddress.IPv4Address(ip))
    firewall = pg_id + "/firewallRules/backend-a-bootstrap-temporary"
    rest(directory, "put", firewall, "2024-08-01", {"properties": {"startIpAddress": ip, "endIpAddress": ip}})
    try:
        url = database_url(values, local=True)
        os.environ.update(
            APP_ENV="production", DATABASE_URL=url, JWT_SECRET=values["jwt"], ENABLE_DEV_SEED="false"
        )
        os.environ.pop("CSFLOW_LOCAL_ONLY", None)
        os.environ["CSFLOW_ENV_FILE"] = str(directory / "does-not-exist.env")
        get_settings.cache_clear()
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        engine = build_engine(
            Settings(_env_file=None, app_env="production", database_url=url, jwt_secret=values["jwt"])
        )
        with session_factory(engine).begin() as session:
            if session.scalar(text("SELECT current_database()")) != DATABASE:
                raise RuntimeError("DEDICATED_DATABASE_REQUIRED")
            result = seed_cloud(session, values["accounts"])
        # Separate runtime identity: no DDL, no role/database creation, no DELETE.
        with engine.begin() as connection:
            raw = connection.connection.driver_connection
            with raw.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='csflow_a_api'")
                if not cursor.fetchone():
                    cursor.execute(
                        sql.SQL("CREATE ROLE csflow_a_api LOGIN PASSWORD {}").format(
                            sql.Literal(values["db_runtime"])
                        )
                    )
                cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                cursor.execute("GRANT CONNECT ON DATABASE backend_a TO csflow_a_api")
                cursor.execute("GRANT USAGE ON SCHEMA public TO csflow_a_api")
                cursor.execute("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO csflow_a_api")
                cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO csflow_a_api")
        engine.dispose()
        account_path = directory / "demo-accounts.json"
        account_path.write_text(
            json.dumps(
                {
                    f"demo-{label}@csflow.example.test": password
                    for label, password in values["accounts"].items()
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        account_path.chmod(0o600)
        print(json.dumps({"migration": "0006", "runtime_role": "DML_WITHOUT_DELETE_OR_DDL", **result}))
    finally:
        status = close_operator_firewall(directory, firewall)
        print("Temporary operator firewall: " + status, flush=True)


def deploy(directory):
    package(directory)
    az(
        "webapp",
        "deploy",
        "-g",
        GROUP,
        "-n",
        APP,
        "--src-path",
        str(directory / "backend-a.zip"),
        "--type",
        "zip",
        "--clean",
        "true",
        "--restart",
        "true",
        "--timeout",
        "1200000",
        "--subscription",
        SUBSCRIPTION,
    )
    print("Linux source build/deployment completed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["provision", "package", "configure", "bootstrap", "deploy"])
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".cache/azure-backend-a")
    args = parser.parse_args()
    directory = args.state_dir.resolve()
    private_directory(directory)
    {
        "provision": provision,
        "package": package,
        "configure": configure,
        "bootstrap": bootstrap,
        "deploy": deploy,
    }[args.command](directory)


if __name__ == "__main__":
    main()
