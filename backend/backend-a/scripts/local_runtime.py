"""Create, use and stop an owned local PostgreSQL cluster; never touch an existing DB."""

import argparse
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy.engine import URL

from scripts.local_support import (
    HIDDEN,
    ROOT,
    free_port,
    local_environment,
    python_command,
    read_state,
    run_checked,
    write_environment,
)


def pg(state, directory, *args):
    executable = "pg_ctl.exe" if os.name == "nt" else "pg_ctl"
    run_checked(
        [str(Path(state["pg_bin"]) / executable), "-D", str(Path(state["cluster_root"]) / "data"), *args],
        env=local_environment(),
        log=directory / "pg-control.log",
    )


def initialize(args):
    directory = args.state_dir.resolve()
    if directory.exists():
        raise ValueError("STATE_DIRECTORY_MUST_BE_NEW")
    directory.mkdir(parents=True)
    runtime_id = uuid4().hex
    cluster = Path(tempfile.mkdtemp(prefix="csflow-local-"))
    (cluster / "owner").write_text(runtime_id)
    state = {
        "runtime_id": runtime_id,
        "state_dir": str(directory),
        "cluster_root": str(cluster),
        "pg_bin": str(args.pg_bin.resolve()),
        "host": "127.0.0.1",
        "db_port": free_port(),
        "api_port": args.api_port or free_port(),
        "database": "csflow_local_" + runtime_id[:12],
        "api_pid": None,
        "fixture_dir": str(args.fixture_dir.resolve()),
    }
    if state["api_port"] == state["db_port"]:
        state["api_port"] = free_port()
    password = secrets.token_urlsafe(32)
    seed_password = os.environ.get("DEV_SEED_PASSWORD") or secrets.token_urlsafe(32)
    pwfile = cluster / "init-password"
    pwfile.write_text(password, encoding="utf-8")
    url = URL.create(
        "postgresql+psycopg",
        username="csflow_test",
        password=password,
        host="127.0.0.1",
        port=state["db_port"],
        database=state["database"],
        query={"sslmode": "disable"},
    ).render_as_string(hide_password=False)
    values = dict(
        APP_ENV="test",
        DATABASE_URL=url,
        JWT_SECRET=secrets.token_urlsafe(64),
        ANALYTICS_SERVICE_SECRET=secrets.token_urlsafe(64),
        ANALYTICS_SERVICE_IDS='["local-synthetic-publisher"]',
        DEV_SEED_PASSWORD=seed_password,
        ENABLE_DEV_SEED="true",
        ALLOWED_HOSTS='["127.0.0.1","localhost","testserver"]',
        CORS_ORIGINS='["http://127.0.0.1:5173"]',
    )
    write_environment(directory / "local.env", values)
    save(directory, state)
    executable = "initdb.exe" if os.name == "nt" else "initdb"
    run_checked(
        [
            str(args.pg_bin / executable),
            "-D",
            str(cluster / "data"),
            "-U",
            "csflow_test",
            "--auth-host=scram-sha-256",
            "--auth-local=trust",
            "--pwfile",
            str(pwfile),
            "--encoding=UTF8",
            "--locale=C",
        ],
        env=local_environment(),
        log=directory / "initdb.log",
    )
    pwfile.unlink()
    with (cluster / "data/postgresql.conf").open("a", encoding="utf-8") as config:
        config.write(
            "\ntimezone='UTC'\nlisten_addresses='127.0.0.1'\nlog_error_verbosity=terse\nlog_parameter_max_length=0\nlog_parameter_max_length_on_error=0\nlog_statement=none\n"
        )
    # pg_ctl must redirect stdout to a file: a background server must not inherit capture pipes.
    control = Path(state["pg_bin"]) / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl")
    with (directory / "pg-start.log").open("w", encoding="utf-8") as output:
        result = subprocess.run(
            [
                str(control),
                "-D",
                str(cluster / "data"),
                "-l",
                str(directory / "postgres.log"),
                "-o",
                f"-p {state['db_port']} -h 127.0.0.1",
                "-w",
                "start",
            ],
            env=local_environment(),
            stdout=output,
            stderr=output,
            creationflags=HIDDEN,
        )
    if result.returncode:
        raise RuntimeError("LOCAL_POSTGRES_START_FAILED")
    try:
        # All connection fields fixed locally, independent of inherited libpq env.
        import psycopg
        from psycopg import sql

        with psycopg.connect(
            host="127.0.0.1",
            port=state["db_port"],
            user="csflow_test",
            password=password,
            dbname="postgres",
            sslmode="disable",
            autocommit=True,
        ) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(state["database"])))
        env = local_environment(directory / "local.env")
        run_checked(
            python_command("-m", "alembic", "upgrade", "head"), env=env, log=directory / "migration.log"
        )
        from app.config import Settings
        from app.db import build_engine, session_factory
        from app.seed import seed_fixture, seed_minimal

        settings = Settings(
            _env_file=None,
            app_env="test",
            database_url=url,
            jwt_secret=values["JWT_SECRET"],
            enable_dev_seed=True,
        )
        engine = build_engine(settings)
        try:
            with session_factory(engine).begin() as session:
                seed_minimal(session, seed_password)
                first = seed_fixture(session, args.fixture_dir.resolve())
            with session_factory(engine).begin() as session:
                seed_minimal(session, seed_password)
                repeat = seed_fixture(session, args.fixture_dir.resolve())
                if sum(repeat["inserted"].values()) != 0:
                    raise RuntimeError("FIXTURE_REPEAT_INSERTED_ROWS")
            (directory / "seed-report.json").write_text(
                json.dumps(
                    {"minimal_repeat": True, "fixture_first": first, "fixture_repeat_inserted": 0}, indent=2
                ),
                encoding="utf-8",
            )
        finally:
            engine.dispose()
    except BaseException:
        pg(state, directory, "-w", "stop", "-m", "fast")
        raise
    print(
        json.dumps(
            {
                "result": "LOCAL_RUNTIME_READY",
                "state_dir": str(directory),
                "api_url": f"http://127.0.0.1:{state['api_port']}",
                "db_host": "127.0.0.1",
                "db_port": state["db_port"],
                "credentials": "saved only in ignored local.env",
            }
        )
    )


def save(directory, state):
    (directory / "runtime.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def start_api(directory):
    directory, state, env = read_state(directory)
    if state.get("api_pid"):
        raise ValueError("API_ALREADY_STARTED_OR_STOP_NOT_CONFIRMED")
    for name in ("api.stop", "api.stopped", "api.started"):
        (directory / name).unlink(missing_ok=True)
    with (directory / "api.log").open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            python_command("-m", "scripts.local_api", "--state-dir", str(directory)),
            cwd=ROOT,
            env=env,
            stdout=output,
            stderr=output,
            creationflags=HIDDEN,
        )
    state["api_pid"] = process.pid
    save(directory, state)
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{state['api_port']}", trust_env=False, timeout=2
        ) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("LOCAL_API_EXITED")
                try:
                    marker = directory / "api.started"
                    if (
                        marker.exists()
                        # Windows venv launchers can have a different PID from
                        # the actual Python server. The private path + runtime
                        # identity is the ownership fence, not PID equality.
                        and marker.read_text(encoding="utf-8").split(":", 1)[0] == state["runtime_id"]
                        and client.get("/health/ready").status_code == 200
                    ):
                        return process
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
        raise RuntimeError("LOCAL_API_NOT_READY")
    except BaseException:
        (directory / "api.stop").touch()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()  # exact process handle created above, never a discovered PID
            process.wait(timeout=5)
        state["api_pid"] = None
        save(directory, state)
        raise


def stop_api(directory, process=None):
    directory, state, _ = read_state(directory)
    (directory / "api.stop").touch()
    if process is not None:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()  # exact owned Popen handle; never a discovered PID
            process.wait(timeout=5)
            state["api_pid"] = None
            save(directory, state)
            raise RuntimeError("API_REQUIRED_FORCE_STOP") from None
    elif state.get("api_pid"):
        deadline = time.monotonic() + 15
        while not (directory / "api.stopped").exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not (directory / "api.stopped").exists():
            raise RuntimeError("API_STOP_NOT_CONFIRMED_NO_PID_KILL_ATTEMPTED")
    state["api_pid"] = None
    save(directory, state)


def stop(directory):
    directory, state, _ = read_state(directory)
    stop_api(directory)
    if (Path(state["cluster_root"]) / "data/postmaster.pid").exists():
        pg(state, directory, "-w", "stop", "-m", "fast")
    if (Path(state["cluster_root"]) / "data/postmaster.pid").exists():
        raise RuntimeError("LOCAL_POSTGRES_STOP_NOT_CONFIRMED")
    print("Owned local API/PostgreSQL stopped; files retained; no other DB touched")


def restart_database(directory):
    directory, state, _ = read_state(directory)
    if (Path(state["cluster_root"]) / "data/postmaster.pid").exists():
        raise ValueError("DATABASE_ALREADY_RUNNING_OR_STOP_NOT_CONFIRMED")
    control = Path(state["pg_bin"]) / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl")
    with (directory / "pg-restart.log").open("w", encoding="utf-8") as output:
        result = subprocess.run(
            [
                str(control),
                "-D",
                str(Path(state["cluster_root"]) / "data"),
                "-l",
                str(directory / "postgres.log"),
                "-o",
                f"-p {state['db_port']} -h 127.0.0.1",
                "-w",
                "start",
            ],
            env=local_environment(),
            stdout=output,
            stderr=output,
            creationflags=HIDDEN,
        )
    if result.returncode:
        raise RuntimeError("LOCAL_POSTGRES_RESTART_FAILED")
    print("Owned PostgreSQL restarted on 127.0.0.1; existing local data retained")


def cleanup(directory):
    import shutil

    directory, state, _ = read_state(directory)
    stop(directory)
    cluster = Path(state["cluster_root"]).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if not cluster.is_relative_to(temp_root) or not cluster.name.startswith("csflow-local-"):
        raise ValueError("CLEANUP_TARGET_OUTSIDE_OWNED_TEMP_ROOT")
    # Identity/owner marker already checked by read_state, and stop is confirmed.
    shutil.rmtree(cluster)
    (directory / "local.env").unlink()
    state["cleaned"] = True
    state["api_pid"] = None  # stop() saved a fresh record; do not reintroduce the old PID
    save(directory, state)
    print("Only this owned temporary cluster and its local credentials removed; reports retained")


def full_tests(directory):
    directory, state, env = read_state(directory)
    # Test fixtures must not inherit this runtime's service auth or .env.
    testenv = local_environment(
        TEST_POSTGRES_URL=env["DATABASE_URL"], CSFLOW_FIXTURE_DIR=state["fixture_dir"], APP_ENV="test"
    )
    run_checked(
        python_command(
            "-m",
            "pytest",
            "-q",
            "--database=postgres",
            "--basetemp=" + str(directory / "pytest-temp"),
            "--junitxml=" + str(directory / "postgres-results.xml"),
            "--tb=short",
            "-x",
        ),
        env=testenv,
        log=directory / "pytest.log",
    )
    import xml.etree.ElementTree as ET

    suite = ET.parse(directory / "postgres-results.xml").getroot()[0]
    print(json.dumps({k: suite.attrib[k] for k in ("tests", "errors", "failures", "skipped", "time")}))


def main():
    # Do this unconditionally, before any connection. No inherited marker can
    # bypass removal of cloud credentials, libpq service settings or proxies.
    extra = (
        {"DEV_SEED_PASSWORD": os.environ["DEV_SEED_PASSWORD"]} if os.environ.get("DEV_SEED_PASSWORD") else {}
    )
    isolated = local_environment(**extra)
    os.environ.clear()
    os.environ.update(isolated)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init")
    init.add_argument("--pg-bin", type=Path, required=True)
    init.add_argument("--fixture-dir", type=Path, default=ROOT / "reference/fixture")
    init.add_argument("--api-port", type=int, choices=range(1024, 65536), metavar="PORT")
    for name in ("start-api", "start-db", "stop", "clean", "verify", "test"):
        sub.add_parser(name)
    for child in sub.choices.values():
        child.add_argument("--state-dir", type=Path, default=ROOT / ".cache/local-phase5")
    args = parser.parse_args()
    try:
        if args.action == "init":
            initialize(args)
        elif args.action == "start-api":
            start_api(args.state_dir)
            directory, state, _ = read_state(args.state_dir)
            print(f"Local API ready: http://127.0.0.1:{state['api_port']}/docs; use local_runtime stop")
        elif args.action == "start-db":
            restart_database(args.state_dir)
        elif args.action == "clean":
            cleanup(args.state_dir)
        elif args.action == "stop":
            stop(args.state_dir)
        elif args.action == "test":
            full_tests(args.state_dir)
        else:
            from scripts.http_integration import verify

            verify(args.state_dir)
    except Exception as exc:
        import re

        code = str(exc) if re.fullmatch(r"[A-Z0-9_]+", str(exc)) else "LOCAL_OPERATION_FAILED"
        print(code + ": inspect ignored local logs; no credentials printed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
