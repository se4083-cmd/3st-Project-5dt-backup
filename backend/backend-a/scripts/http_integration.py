"""PostgreSQL + real Uvicorn acceptance, in a new schema of an owned local runtime."""

import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.db import build_engine, session_factory
from app.seed import seed_fixture, seed_minimal
from scripts.local_runtime import save, start_api, stop_api
from scripts.local_support import (
    free_port,
    local_environment,
    python_command,
    read_state,
    run_checked,
    write_environment,
)
from tests.http_scenario import CUSTOMER_TEXT, FIXED_REPLY, PRIVATE, run


def verify(state_dir):
    directory, state, env = read_state(state_dir)
    schema = "http_csflow_" + uuid4().hex
    work = directory / schema
    work.mkdir()
    base = build_engine(
        Settings(
            _env_file=None, app_env="test", database_url=env["DATABASE_URL"], jwt_secret=env["JWT_SECRET"]
        )
    )
    engine = None
    process = None
    success = False
    try:
        with base.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        child = {**state, "state_dir": str(work), "api_port": free_port(), "api_pid": None}
        save(work, child)
        values = {
            k: env[k]
            for k in (
                "APP_ENV",
                "DATABASE_URL",
                "JWT_SECRET",
                "ANALYTICS_SERVICE_SECRET",
                "ANALYTICS_SERVICE_IDS",
                "DEV_SEED_PASSWORD",
                "ENABLE_DEV_SEED",
                "ALLOWED_HOSTS",
                "CORS_ORIGINS",
            )
        }
        values["DATABASE_URL"] = (
            make_url(values["DATABASE_URL"])
            .update_query_dict({"options": f"-csearch_path={schema}"})
            .render_as_string(hide_password=False)
        )
        write_environment(work / "local.env", values)
        childenv = local_environment(work / "local.env")
        run_checked(
            python_command("-m", "alembic", "upgrade", "head"), env=childenv, log=work / "migration.log"
        )
        engine = build_engine(
            Settings(
                _env_file=None,
                app_env="test",
                database_url=values["DATABASE_URL"],
                jwt_secret=values["JWT_SECRET"],
            )
        )
        factory = session_factory(engine)
        with factory.begin() as session:
            seed_minimal(session, env["DEV_SEED_PASSWORD"])
            seed_fixture(session, Path(state["fixture_dir"]))
        process = start_api(work)
        with httpx.Client(
            base_url=f"http://127.0.0.1:{child['api_port']}", trust_env=False, timeout=30
        ) as client:
            if client.get("/health/live").json() != {"status": "alive"} or client.get(
                "/health/ready"
            ).json() != {"status": "ready"}:
                raise RuntimeError("HEALTH_FAILED")
            report = run(client, factory, env, Path(state["fixture_dir"]))
            actual = client.get("/openapi.json").json()
            expected = json.loads(
                (Path(__file__).resolve().parents[1] / "docs/openapi.json").read_text(encoding="utf-8")
            )
            if actual != expected:
                raise RuntimeError("OPENAPI_FILE_DIFFERS_FROM_RUNNING_API")
        success = True
    finally:
        if process is not None:
            stop_api(work, process)
        if engine is not None:
            engine.dispose()
        # Exact random schema generated above, never an operator-supplied DROP target.
        with base.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()
        (work / "local.env").unlink(missing_ok=True)
        if process is not None and not (work / "api.stopped").exists():
            raise RuntimeError("GRACEFUL_SHUTDOWN_NOT_OBSERVED")
    if success:
        output = (work / "api.log").read_text(encoding="utf-8") + (directory / "postgres.log").read_text(
            encoding="utf-8"
        )
        import re

        if re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", output):
            raise RuntimeError("HTTP_LOG_TOKEN_PATTERN_FOUND")
        for value in (
            env["DEV_SEED_PASSWORD"],
            env["JWT_SECRET"],
            env["ANALYTICS_SERVICE_SECRET"],
            CUSTOMER_TEXT,
            FIXED_REPLY,
            PRIVATE,
            "PRIVATE_",
        ):
            if value in output:
                raise RuntimeError("HTTP_LOG_SENSITIVE_VALUE_FOUND")
        report.update(
            transport="real Uvicorn HTTP on 127.0.0.1",
            database="PostgreSQL",
            schema_removed=True,
            api_gracefully_stopped=True,
            openapi_matches=True,
            logs_sensitive_values_absent=True,
        )
        (directory / "http-integration-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "result",
                        "source",
                        "transport",
                        "database",
                        "checks",
                        "schema_removed",
                        "api_gracefully_stopped",
                        "openapi_matches",
                    )
                }
            )
        )


if __name__ == "__main__":
    # The public CLI sanitizes inherited environment before any connection.
    os.execv(
        __import__("sys").executable,
        [__import__("sys").executable, "-m", "scripts.local_runtime", "verify", *__import__("sys").argv[1:]],
    )
