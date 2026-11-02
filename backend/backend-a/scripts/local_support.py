"""Shared local harness utilities. No inherited credentials or proxy settings."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

from app.local_guard import require_local_database

ROOT = Path(__file__).resolve().parents[1]
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def write_environment(path, values):
    # Quoting preserves spaces/#/quotes in an operator's local seed password.
    Path(path).write_text(
        "\n".join(k + "=" + json.dumps(v, ensure_ascii=False) for k, v in values.items()) + "\n",
        encoding="utf-8",
    )


def local_environment(env_file=None, **extra):
    # Deliberate allowlist: excludes AZURE_*, ARM_*, AWS_*, GITHUB_*, OPENAI_*,
    # PG*, proxy variables, PYTHONPATH and existing app configuration.
    keep = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "LOCALAPPDATA",
        "APPDATA",
        "USERPROFILE",
        "HOME",
        "LANG",
    }
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update(
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        PYTHONNOUSERSITE="1",
        CSFLOW_LOCAL_ONLY="1",
        HTTP_PROXY="",
        HTTPS_PROXY="",
        ALL_PROXY="",
        NO_PROXY="127.0.0.1",
        UV_NO_CONFIG="1",
    )
    if env_file is not None:
        path = Path(env_file).resolve()
        values = dotenv_values(path, interpolate=False)
        permitted = {
            "APP_ENV",
            "DATABASE_URL",
            "JWT_SECRET",
            "ANALYTICS_SERVICE_SECRET",
            "ANALYTICS_SERVICE_IDS",
            "DEV_SEED_PASSWORD",
            "ENABLE_DEV_SEED",
            "ALLOWED_HOSTS",
            "CORS_ORIGINS",
        }
        if set(values) - permitted or not all(isinstance(v, str) for v in values.values()):
            raise ValueError("UNREVIEWED_LOCAL_ENV_FILE")
        require_local_database(values["DATABASE_URL"], postgres_only=True)
        env.update(values, CSFLOW_ENV_FILE=str(path))
    else:
        env["CSFLOW_ENV_FILE"] = str(ROOT / ".cache/nonexistent-isolated.env")
    env.update(extra)
    return env


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_checked(args, *, env, log):
    result = subprocess.run(
        args, cwd=ROOT, env=env, capture_output=True, encoding="utf-8", errors="replace", creationflags=HIDDEN
    )
    # No shell command line or exception echo. Redact known local secrets even on failure.
    output = result.stdout + result.stderr
    for key in (
        "DATABASE_URL",
        "JWT_SECRET",
        "ANALYTICS_SERVICE_SECRET",
        "DEV_SEED_PASSWORD",
        "TEST_POSTGRES_URL",
    ):
        if env.get(key):
            output = output.replace(env[key], "[REDACTED]")
    Path(log).write_text(output, encoding="utf-8")
    if result.returncode:
        raise RuntimeError("LOCAL_SUBPROCESS_FAILED")


def read_state(directory):
    directory = Path(directory).resolve()
    state = json.loads((directory / "runtime.json").read_text(encoding="utf-8"))
    if state["state_dir"] != str(directory) or state["host"] != "127.0.0.1":
        raise ValueError("LOCAL_RUNTIME_IDENTITY_MISMATCH")
    cluster = Path(state["cluster_root"]).resolve()
    if not cluster.name.startswith("csflow-local-") or (cluster / "owner").read_text() != state["runtime_id"]:
        raise ValueError("LOCAL_CLUSTER_OWNERSHIP_MISMATCH")
    env = local_environment(directory / "local.env")
    url = require_local_database(env["DATABASE_URL"], postgres_only=True)
    if url.port != state["db_port"] or url.database != state["database"]:
        raise ValueError("LOCAL_DATABASE_IDENTITY_MISMATCH")
    return directory, state, env


def python_command(*args):
    return [sys.executable, *args]
