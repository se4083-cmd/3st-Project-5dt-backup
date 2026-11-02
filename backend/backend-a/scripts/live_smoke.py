"""Real loopback HTTP smoke test using an isolated SQLite DB, never PostgreSQL evidence."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / ".cache" / ("live-smoke-" + uuid4().hex)
    folder.mkdir(parents=True)
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": "sqlite+pysqlite:///" + (folder / "app.db").as_posix(),
        "JWT_SECRET": secrets.token_urlsafe(64),
        "ENABLE_DEV_SEED": "true",
        "DEV_SEED_PASSWORD": secrets.token_urlsafe(24),
    }
    for command in [["-m", "alembic", "upgrade", "head"], ["-m", "app.seed", "minimal"]]:
        subprocess.run([sys.executable, *command], cwd=ROOT, env=env, check=True, capture_output=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (folder / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
                for _ in range(100):
                    try:
                        if client.get("/health/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if server.poll() is not None:
                        raise RuntimeError("Smoke server exited; inspect local server.log")
                    time.sleep(0.2)
                else:
                    raise RuntimeError("Smoke server failed readiness")

                def login(label):
                    response = client.post(
                        "/api/v1/auth/login",
                        json={
                            "login_name": f"dev-{label}@example.test",
                            "password": env["DEV_SEED_PASSWORD"],
                        },
                    )
                    response.raise_for_status()
                    return {"Authorization": "Bearer " + response.json()["access_token"]}

                own = login("customer1")
                order = client.get("/api/v1/orders", headers=own).json()["items"][0]
                result = client.post(
                    "/api/v1/tickets",
                    headers={**own, "Idempotency-Key": "live-smoke-ticket"},
                    json={"order_id": order["order_id"], "message": "합성 배송 상태 문의"},
                )
                assert result.status_code == 201
                ticket_id = result.json()["ticket_id"]
                detail = client.get(f"/api/v1/tickets/{ticket_id}", headers=own)
                assert detail.status_code == 200 and detail.json()["stage"] == "RECEIVED"
                other = login("customer2")
                assert client.get(f"/api/v1/tickets/{ticket_id}", headers=other).status_code == 404
                assert client.get(f"/api/v1/orders/{order['order_id']}", headers=other).status_code == 404
                reopened = client.post(
                    f"/api/v1/tickets/{ticket_id}/reopen",
                    headers={**own, "Idempotency-Key": "live-smoke-reopen"},
                    json={"expected_revision": detail.json()["revision"], "message": "추가 문의"},
                )
                assert reopened.status_code == 201 and reopened.json()["cycle_no"] == 2
                handoff_body = {
                    "expected_revision": reopened.json()["revision"],
                    "message": "상담사 연결 요청",
                    "reason_code": "CUSTOMER_REQUEST",
                }
                handoff = client.post(
                    f"/api/v1/tickets/{ticket_id}/request-agent",
                    headers={**own, "Idempotency-Key": "live-smoke-handoff"},
                    json=handoff_body,
                )
                assert handoff.status_code == 201 and handoff.json()["handling_mode"] == "HUMAN"
                replay = client.post(
                    f"/api/v1/tickets/{ticket_id}/request-agent",
                    headers={**own, "Idempotency-Key": "live-smoke-handoff"},
                    json=handoff_body,
                )
                assert replay.status_code == 200 and replay.json() == handoff.json()
                # Explicit local fixture only: no B assignment/response engine is exercised.
                setup = """
import os
from uuid import uuid4
from sqlalchemy import select
from app.config import get_settings
from app.db import build_engine, session_factory, utcnow
from app.models import assignments, tickets
from app.seed import stable_id
engine=build_engine(get_settings())
with session_factory(engine).begin() as session:
    ticket_id=os.environ['SMOKE_TICKET_ID']
    ticket=session.execute(select(tickets).where(tickets.c.ticket_id==ticket_id)).mappings().one()
    session.execute(tickets.update().where(tickets.c.ticket_id==ticket_id).values(
        team_id=stable_id('team'), status='IN_PROGRESS', category='DELIVERY'))
    session.execute(assignments.insert().values(assignment_id=str(uuid4()),ticket_id=ticket_id,
        cycle_no=ticket['cycle_no'],team_id=stable_id('team'),agent_id=stable_id('agent'),
        assigned_at=utcnow(),reason_code='TEST_FIXTURE_ONLY'))
engine.dispose()
"""
                subprocess.run(
                    [sys.executable, "-c", setup],
                    cwd=ROOT,
                    env={**env, "SMOKE_TICKET_ID": ticket_id},
                    check=True,
                    capture_output=True,
                )
                agent = login("agent")
                # Development seed identity is fixture data; compute it in the isolated child.
                ids_code = "from app.seed import stable_id; import json; print(json.dumps({k:stable_id(k) for k in ['team','agent','customer1/profile']}))"
                ids = json.loads(
                    subprocess.run(
                        [sys.executable, "-c", ids_code],
                        cwd=ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        check=True,
                    ).stdout
                )
                followup = client.post(
                    "/api/v1/staff/followups",
                    headers={**agent, "Idempotency-Key": "live-followup-create"},
                    json={
                        "ticket_id": ticket_id,
                        "owner_team_id": ids["team"],
                        "owner_user_id": ids["agent"],
                        "kind": "CHECK",
                        "public_note": "확인 중",
                        "internal_note": "PRIVATE_SMOKE_NOTE",
                        "blocks_resolution": True,
                    },
                )
                assert followup.status_code == 201
                action_id = followup.json()["action_id"]
                public = client.get(f"/api/v1/followups/{action_id}", headers=own)
                assert (
                    public.status_code == 200
                    and "PRIVATE" not in public.text
                    and "owner_user_id" not in public.text
                )
                view = client.post(
                    f"/api/v1/staff/customers/{ids['customer1/profile']}/360",
                    headers=agent,
                    json={"purpose_code": "ACTIVE_SUPPORT"},
                )
                assert view.status_code == 200 and view.json()["total_ticket_count"] == 1
                assert view.json()["followup_count"] == 1
                done = client.post(
                    f"/api/v1/staff/followups/{action_id}/status",
                    headers=agent,
                    json={"expected_revision": 1, "status": "DONE"},
                )
                assert done.status_code == 200
                assert client.get(f"/api/v1/tickets/{ticket_id}", headers=own).json()["stage"] == "IN_SUPPORT"
                for operation in ("reopen", "request-agent"):
                    body = {"expected_revision": 3, "message": "타고객 요청 차단"}
                    if operation == "request-agent":
                        body["reason_code"] = "OTHER"
                    assert (
                        client.post(
                            f"/api/v1/tickets/{ticket_id}/{operation}",
                            headers={**other, "Idempotency-Key": f"other-{operation}-key"},
                            json=body,
                        ).status_code
                        == 404
                    )
                # Inspect the durable row after the HTTP transaction committed.
                import sqlite3

                with sqlite3.connect(folder / "app.db") as db:
                    assert (
                        db.execute("SELECT count(*) FROM automation_jobs WHERE status='PENDING'").fetchone()[
                            0
                        ]
                        == 1
                    )
                    assert (
                        db.execute(
                            "SELECT count(*) FROM automation_jobs WHERE job_kind='HANDOFF'"
                        ).fetchone()[0]
                        == 1
                    )
                    assert (
                        db.execute(
                            "SELECT count(*) FROM automation_jobs WHERE status='CANCELLED'"
                        ).fetchone()[0]
                        == 2
                    )
                print(
                    json.dumps(
                        {
                            "engine": "SQLite",
                            "transport": "HTTP on loopback",
                            "result": "PASS",
                            "checks": [
                                "login",
                                "own_order",
                                "ticket",
                                "reopen",
                                "agent_request",
                                "agent_idempotency",
                                "durable_handoff",
                                "ownership_denial",
                                "followup_crud",
                                "scoped_customer360",
                                "no_internal_note_leak",
                            ],
                            "assignment_setup": "local test fixture; B engine not executed",
                        }
                    )
                )
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
