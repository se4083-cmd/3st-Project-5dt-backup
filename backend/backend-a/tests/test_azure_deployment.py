import json
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.auth import verify_password
from app.local_guard import require_local_database
from app.models import users
from app.public_limits import PublicLimits
from app.seed import stable_id
from app.staff_models import automation_control, staff_permissions
from scripts import azure_deploy
from scripts.azure_bootstrap import cloud_id, seed_cloud


async def echo(request: Request):
    body = await request.body()
    return JSONResponse({"bytes": len(body)})


def limited_client(**kwargs):
    app = Starlette(routes=[Route("/{path:path}", echo, methods=["POST"])])
    return TestClient(PublicLimits(app, **kwargs))


def test_public_body_limit_and_chunk_boundaries():
    with limited_client(body_bytes=12, analytics_bytes=24) as client:
        assert client.post("/ordinary", content=b"a" * 12).status_code == 200
        response = client.post("/ordinary", content=b"a" * 13)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"
        assert client.post("/api/v1/analytics/batches", content=b"a" * 24).status_code == 200
        assert client.post("/api/v1/analytics/batches", content=b"a" * 25).status_code == 413


def test_login_limit_normalizes_account_and_does_not_store_identifiers():
    app = PublicLimits(Starlette(routes=[Route("/{path:path}", echo, methods=["POST"])]), login_attempts=2)
    with TestClient(app) as client:
        for name in ("SYNTHETIC@EXAMPLE.TEST", " synthetic@example.test "):
            assert client.post("/api/v1/auth/login", json={"login_name": name}).status_code == 200
        response = client.post("/api/v1/auth/login", json={"login_name": "synthetic@example.test"})
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"
        assert "synthetic@" not in json.dumps(list(app.buckets))
        assert "testclient" not in json.dumps(list(app.buckets))


def test_limit_expires_and_capacity_fails_closed(monkeypatch):
    app = PublicLimits(Starlette())
    monkeypatch.setattr("app.public_limits.time.monotonic", lambda: 100)
    assert app.allow("a", 1)
    assert not app.allow("a", 1)
    monkeypatch.setattr("app.public_limits.time.monotonic", lambda: 161)
    assert app.allow("a", 1)
    for i in range(4095):
        assert app.allow(str(i), 1)
    assert not app.allow("new", 1)


def test_local_guard_still_rejects_azure_database():
    with pytest.raises(ValueError, match="LOCAL_DATABASE_REQUIRED"):
        require_local_database(
            "postgresql+psycopg://x:x@dedicated.postgres.database.azure.com:5432/backend_a?sslmode=verify-full"
        )


def test_missing_deployment_secret_state_never_rotates_existing_keys(tmp_path):
    with pytest.raises(RuntimeError, match="DEPLOYMENT_SECRET_STATE_REQUIRED"):
        azure_deploy.state(tmp_path)
    assert not (tmp_path / "secrets.json").exists()


def test_shared_delete_lock_closes_only_own_temporary_rule(monkeypatch, tmp_path):
    calls = []

    def fake_rest(directory, method, resource, api, body=None):
        calls.append((method, resource, body))
        if method == "delete":
            raise RuntimeError("ScopeLocked")

    monkeypatch.setattr(azure_deploy, "rest", fake_rest)
    resource = (
        azure_deploy.BASE
        + f"Microsoft.DBforPostgreSQL/flexibleServers/{azure_deploy.PG}/firewallRules/backend-a-bootstrap-temporary"
    )
    result = azure_deploy.close_operator_firewall(tmp_path, resource)
    assert result == "DISABLED_LOOPBACK_SHARED_DELETE_LOCK"
    assert calls[-1][2]["properties"] == {"startIpAddress": "127.0.0.1", "endIpAddress": "127.0.0.1"}
    with pytest.raises(RuntimeError, match="ONLY_OWN_TEMPORARY_RULE_ALLOWED"):
        azure_deploy.close_operator_firewall(tmp_path, resource + "-other-team")


def test_cloud_seed_keeps_development_locked_and_pause_idempotent(app):
    passwords = {k: secrets.token_urlsafe(32) for k in ("customer1", "customer2", "agent", "admin")}
    with app.state.session_factory.begin() as session:
        result = seed_cloud(session, passwords)
        old = dict(session.execute(select(automation_control)).mappings().one())
        user = session.execute(select(users).where(users.c.user_id == cloud_id("customer1"))).mappings().one()
        assert verify_password(passwords["customer1"], user["password_hash"])
        saved = user["password_hash"]
        assert not user["is_dev_account"]
        assert session.scalar(select(users.c.is_dev_account).where(users.c.user_id == stable_id("customer1")))
        assert old["paused"]
        assert result["full_fixture_loaded"] is False
        granted = set(
            session.scalars(
                select(staff_permissions.c.permission).where(staff_permissions.c.user_id == cloud_id("admin"))
            )
        )
        assert "RETENTION_TEAM_REVIEW" in granted
        assert not {"AUTOMATION_RESUME", "RETENTION_GLOBAL_REVIEW", "UNROUTED_QUEUE_READ"} & granted
    with app.state.session_factory.begin() as session:
        seed_cloud(session, {k: secrets.token_urlsafe(32) for k in passwords})
        assert dict(session.execute(select(automation_control)).mappings().one()) == old
        assert (
            session.scalar(select(users.c.password_hash).where(users.c.user_id == cloud_id("customer1")))
            == saved
        )
