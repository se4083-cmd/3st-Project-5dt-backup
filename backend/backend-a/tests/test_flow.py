from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import func, select

from app import audit
from app.db import utcnow
from app.model_constraints import idempotency_keys
from app.models import assignments, audit_events, automation_jobs, messages, tickets, users
from app.seed import stable_id
from tests.conftest import PASSWORD, login_as


def submit(client, headers, *, key="ticket-test-0001", message="배송 상태를 알려주세요", order=None):
    return client.post(
        "/api/v1/tickets",
        json={"message": message, "order_id": order},
        headers={**headers, "Idempotency-Key": key},
    )


def counts(app):
    with app.state.session_factory() as session:
        return {
            t.name: session.scalar(select(func.count()).select_from(t))
            for t in (tickets, messages, automation_jobs, idempotency_keys)
        }


def test_login_success_failure_and_disabled(client, app):
    success = client.post(
        "/api/v1/auth/login", json={"login_name": "dev-customer1@example.test", "password": PASSWORD}
    )
    assert success.status_code == 200
    for name, pw in [("dev-customer1@example.test", "wrong"), ("missing@example.test", PASSWORD)]:
        denied = client.post("/api/v1/auth/login", json={"login_name": name, "password": pw})
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "INVALID_CREDENTIALS"
    with app.state.session_factory.begin() as session:
        session.execute(users.update().where(users.c.user_id == stable_id("customer1")).values(active=False))
    assert (
        client.post(
            "/api/v1/auth/login", json={"login_name": "dev-customer1@example.test", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer " + success.json()["access_token"]}
        ).status_code
        == 401
    )


def test_auth_contract(client, headers, app):
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert set(me.json()) == {"user_id", "login_name", "role"}
    assert client.get("/api/v1/orders").status_code == 401
    assert client.get("/api/v1/orders", headers={"Authorization": "Bearer malformed"}).status_code == 401
    token = jwt.encode(
        {
            "sub": stable_id("customer1"),
            "exp": utcnow() - timedelta(seconds=5),
            "iat": utcnow() - timedelta(minutes=10),
            "nbf": utcnow() - timedelta(minutes=10),
            "iss": "cs-flow-ai",
            "aud": "cs-flow-api",
        },
        app.state.settings.jwt_secret,
        algorithm="HS256",
    )
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_disabled_fixture_password_is_never_a_login_hash(client, app):
    with app.state.session_factory.begin() as session:
        session.execute(
            users.update()
            .where(users.c.user_id == stable_id("customer1"))
            .values(password_hash="!DISABLED_SYNTHETIC_LOGIN")
        )
    for password in (PASSWORD, "!DISABLED_SYNTHETIC_LOGIN", "unusable-dummy-verification-value"):
        assert (
            client.post(
                "/api/v1/auth/login", json={"login_name": "dev-customer1@example.test", "password": password}
            ).status_code
            == 401
        )


def test_end_to_end_with_order(client, headers, app):
    own = client.get("/api/v1/orders", headers=headers)
    assert own.status_code == 200
    assert len(own.json()["items"]) == 3
    order = own.json()["items"][0]
    assert client.get(f"/api/v1/orders/{order['order_id']}", headers=headers).status_code == 200
    before = utcnow()
    created = submit(client, headers, order=order["order_id"])
    assert created.status_code == 201, created.text
    ticket_id = created.json()["ticket_id"]
    detail = client.get(f"/api/v1/tickets/{ticket_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["stage"] == "RECEIVED"
    assert detail.json()["handling_mode"] == "AUTOMATED"
    assert detail.json()["product_id"] == order["product_id"]
    assert len(detail.json()["messages"]) == 1
    assert client.get("/api/v1/tickets", headers=headers).json()["items"][0]["ticket_id"] == ticket_id
    assert len(client.get(f"/api/v1/tickets/{ticket_id}/messages", headers=headers).json()["items"]) == 1
    with app.state.session_factory() as session:
        job = (
            session.execute(select(automation_jobs).where(automation_jobs.c.ticket_id == ticket_id))
            .mappings()
            .one()
        )
        assert job["status"] == "PENDING" and job["expected_ticket_version"] == 1 and job["cycle_no"] == 1
        ticket = session.execute(select(tickets).where(tickets.c.ticket_id == ticket_id)).mappings().one()
        assert ticket["created_at"] >= before and ticket["created_at"].utcoffset() == timedelta(0)
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_events)
                .where(audit_events.c.ticket_id == ticket_id, audit_events.c.action == "TICKET_CREATED")
            )
            == 1
        )


def test_other_customers_hidden_and_denial_audit_survives(client, headers, app):
    other = login_as(client, "customer2")
    foreign_order = client.get("/api/v1/orders", headers=other).json()["items"][0]["order_id"]
    foreign_ticket = submit(client, other).json()["ticket_id"]
    for path in [
        f"/api/v1/orders/{foreign_order}",
        f"/api/v1/tickets/{foreign_ticket}",
        f"/api/v1/tickets/{foreign_ticket}/messages",
    ]:
        assert client.get(path, headers=headers).status_code == 404
    before = counts(app)
    assert submit(client, headers, order=foreign_order).status_code == 404
    assert counts(app) == before
    assert client.get("/api/v1/tickets", headers=headers).json()["items"] == []
    with app.state.session_factory() as session:
        denied = (
            session.execute(select(audit_events).where(audit_events.c.result == "DENIED")).mappings().all()
        )
        assert len(denied) == 4
        assert all(x["payload"] == {} for x in denied)


def test_general_faq_and_body_identity_rejected(client, headers):
    created = submit(client, headers)
    assert created.status_code == 201
    detail = client.get("/api/v1/tickets/" + created.json()["ticket_id"], headers=headers).json()
    assert detail["order_id"] is None and detail["product_id"] is None
    for injected in [
        {"customer_id": stable_id("customer2/profile")},
        {"role": "ADMIN"},
        {"product_id": str(uuid4())},
    ]:
        response = client.post(
            "/api/v1/tickets",
            headers={**headers, "Idempotency-Key": "unsafe-key-01"},
            json={"message": "hello", **injected},
        )
        assert response.status_code == 422


@pytest.mark.parametrize("message", ["", "   ", "x" * 10001])
def test_input_validation(client, headers, message):
    assert submit(client, headers, message=message).status_code == 422


def test_atomic_rollback_if_audit_fails(client, headers, app, monkeypatch):
    before = counts(app)
    original = audit.record

    def fail_after_writes(*args, **kwargs):
        if args[2] == "TICKET_CREATED":
            raise RuntimeError("test failure after all domain inserts")
        return original(*args, **kwargs)

    monkeypatch.setattr(audit, "record", fail_after_writes)
    result = submit(client, headers)
    assert result.status_code == 500
    assert counts(app) == before
    with app.state.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_events)
                .where(audit_events.c.action == "TICKET_CREATED")
            )
            == 0
        )


def test_idempotency_retry_conflict_and_per_user_scope(client, headers, app):
    first = submit(client, headers)
    replay = submit(client, headers)
    assert first.status_code == 201 and replay.status_code == 200
    assert first.json() == replay.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert submit(client, headers, message="다른 요청").status_code == 409
    other = submit(client, login_as(client, "customer2"))
    assert other.status_code == 201 and other.json() != first.json()
    assert counts(app) == {"tickets": 2, "messages": 2, "automation_jobs": 2, "idempotency_keys": 2}


def test_concurrent_duplicate_submission(client, headers, app):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: submit(client, headers), range(4)))
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201], [r.text for r in results]
    assert len({r.json()["ticket_id"] for r in results}) == 1
    assert counts(app) == {"tickets": 1, "messages": 1, "automation_jobs": 1, "idempotency_keys": 1}


def test_concurrent_key_with_different_requests_conflicts(client, headers, app):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda value: submit(client, headers, message=value), ["first", "second"])
        )
    assert sorted(r.status_code for r in results) == [201, 409]
    assert counts(app) == {"tickets": 1, "messages": 1, "automation_jobs": 1, "idempotency_keys": 1}


def test_no_internal_fields_or_notes(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    with app.state.session_factory.begin() as session:
        session.execute(
            messages.insert().values(
                message_id=str(uuid4()),
                ticket_id=ticket_id,
                cycle_no=1,
                role="AGENT",
                direction="INTERNAL",
                body="SECRET_INTERNAL_MEMO",
                visibility="INTERNAL",
            )
        )
        session.execute(
            tickets.update().where(tickets.c.ticket_id == ticket_id).values(last_error_code="SECRET_ERROR")
        )
    detail = client.get(f"/api/v1/tickets/{ticket_id}", headers=headers)
    assert "SECRET" not in detail.text
    assert not (
        {"version", "last_error_code", "approval_id", "gate_results", "customer_id"} & set(detail.json())
    )
    assert set(detail.json()["messages"][0]) == {"message_id", "cycle_no", "sender", "body", "created_at"}
    assert "SECRET" not in client.get(f"/api/v1/tickets/{ticket_id}/messages", headers=headers).text


def test_stable_keyset_pagination(client, headers):
    first = client.get("/api/v1/orders?limit=1", headers=headers).json()
    seen = [first["items"][0]["order_id"]]
    cursor = first["next_cursor"]
    while cursor:
        page = client.get("/api/v1/orders", params={"limit": 1, "cursor": cursor}, headers=headers).json()
        seen += [x["order_id"] for x in page["items"]]
        cursor = page["next_cursor"]
    assert len(seen) == len(set(seen)) == 3
    assert client.get("/api/v1/orders?cursor=bad", headers=headers).status_code == 422
    assert client.get("/api/v1/orders?limit=101", headers=headers).status_code == 422


def test_agent_and_admin_scopes(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    agent = login_as(client, "agent")
    admin = login_as(client, "admin")
    assert client.get(f"/api/v1/tickets/{ticket_id}", headers=admin).status_code == 404
    with app.state.session_factory.begin() as session:
        session.execute(
            tickets.update()
            .where(tickets.c.ticket_id == ticket_id)
            .values(team_id=stable_id("team"), category="DELIVERY", status="ASSIGNED")
        )
        session.execute(
            assignments.insert().values(
                assignment_id=str(uuid4()),
                ticket_id=ticket_id,
                cycle_no=1,
                team_id=stable_id("team"),
                agent_id=stable_id("agent"),
                assigned_at=utcnow(),
                reason_code="TEST",
            )
        )
    assert client.get(f"/api/v1/tickets/{ticket_id}", headers=agent).status_code == 200
    assert client.get(f"/api/v1/tickets/{ticket_id}", headers=admin).status_code == 200
    for values in [
        dict(status="RESOLVED", resolved_at=utcnow(), resolution_mode="HUMAN"),
        dict(status="ASSIGNED", category="PAYMENT"),
        dict(category="DELIVERY", cycle_no=2),
    ]:
        with app.state.session_factory.begin() as session:
            session.execute(tickets.update().where(tickets.c.ticket_id == ticket_id).values(**values))
        assert client.get(f"/api/v1/tickets/{ticket_id}", headers=agent).status_code == 404
        assert client.get("/api/v1/tickets", headers=agent).json()["items"] == []
    with app.state.session_factory.begin() as session:
        from app.model_constraints import user_team_scopes

        session.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
    assert client.get(f"/api/v1/tickets/{ticket_id}", headers=admin).status_code == 404
    assert client.get("/api/v1/orders", headers=admin).status_code == 403


def test_health_and_openapi(client):
    assert client.get("/health/live").json() == {"status": "alive"}
    assert client.get("/health/ready").status_code == 200
    doc = client.get("/openapi.json").json()
    assert "/api/v1/tickets" in doc["paths"]
    assert "security" in doc["paths"]["/api/v1/tickets"]["post"]
    assert "200" in doc["paths"]["/api/v1/tickets"]["post"]["responses"]
    for endpoint in ("reopen", "request-agent"):
        route = doc["paths"]["/api/v1/tickets/{ticket_id}/" + endpoint]["post"]
        assert "security" in route and "200" in route["responses"] and "201" in route["responses"]


def test_no_sensitive_request_logging(client, headers, caplog):
    with caplog.at_level("INFO"):
        assert submit(client, headers, message="PRIVATE_COUNSELING_CONTENT").status_code == 201
        response = client.post(
            "/api/v1/auth/login",
            json={"login_name": "dev-customer1@example.test", "password": "PRIVATE_PASSWORD"},
        )
    assert response.status_code == 401
    assert "PRIVATE_" not in caplog.text
    assert headers["Authorization"] not in caplog.text
    assert PASSWORD not in caplog.text
