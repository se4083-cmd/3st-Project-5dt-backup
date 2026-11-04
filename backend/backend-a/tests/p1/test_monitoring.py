from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db import utcnow
from app.model_constraints import user_team_scopes
from app.models import automation_jobs, teams, tickets, users
from app.seed import stable_id
from app.staff_models import automation_control
from tests.analytics_helpers import publish
from tests.conftest import login_as
from tests.phase6_helpers import grant, route
from tests.test_flow import submit

BASE = "/api/v1/admin/p1"


@pytest.fixture(autouse=True)
def enable(monkeypatch):
    monkeypatch.setenv("P1_ENABLED", "true")


def monitor(client, app, *grants):
    grant(app, "admin", "P1_MONITOR_READ", *grants)
    return login_as(client, "admin")


def test_disabled_keeps_p0_alive(client, app, monkeypatch):
    h = monitor(client, app)
    monkeypatch.setenv("P1_ENABLED", "false")
    assert client.get(BASE + "/session", headers=h).status_code == 503
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


@pytest.mark.parametrize("role", ["customer1", "agent", "admin"])
def test_no_implicit_role_permission(client, app, role):
    h = login_as(client, role)
    for path in ("/monitoring/summary", "/monitoring/jobs", "/monitoring/ai-calls"):
        assert client.get(BASE + path, headers=h).status_code == 403
    if role != "admin":
        grant(app, role, "P1_MONITOR_READ")
        assert client.get(BASE + "/monitoring/summary", headers=h).status_code == 403


def test_bridge_uses_active_sql_grants_and_preserves_p0_capabilities(client, app):
    h = monitor(client, app, "AUTOMATION_READ")
    r = client.get(BASE + "/session", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["allowedTeamIds"] == [stable_id("team")]
    assert "P1_MONITOR_READ" in body["permissions"]
    assert "P1_MONITOR_READ" in body["capabilities"]
    assert client.get("/api/v1/staff/capabilities", headers=h).json()["capabilities"] == ["AUTOMATION_READ"]
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
        s.execute(
            users.update()
            .where(users.c.user_id == stable_id("admin"))
            .values(allowed_team_ids=[stable_id("team")])
        )
    assert client.get(BASE + "/session", headers=h).status_code == 403
    assert client.get(BASE + "/monitoring/jobs", headers=h).status_code == 403


def test_filters_reject_other_duplicate_inactive_and_bad_teams(client, app):
    h = monitor(client, app)
    for team in (str(uuid4()), stable_id("team2")):
        assert (
            client.get(BASE + "/monitoring/summary", headers=h, params={"team_ids": team}).status_code == 403
        )
    assert (
        client.get(
            BASE + "/monitoring/summary", headers=h, params=[("team_ids", stable_id("team"))] * 2
        ).status_code
        == 422
    )
    assert client.get(BASE + "/monitoring/jobs", headers=h, params={"team_ids": "bad"}).status_code == 422
    with app.state.session_factory.begin() as s:
        s.execute(teams.update().where(teams.c.team_id == stable_id("team")).values(active=False))
    assert client.get(BASE + "/monitoring/summary", headers=h).status_code == 403


def create_routed(client, headers, app):
    tid = submit(client, headers, key="p1-" + uuid4().hex).json()["ticket_id"]
    route(app, tid)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(team_id=stable_id("team")))
    return tid


def test_summary_scoping_lifecycle_and_sanitized_job_page(client, headers, app):
    h = monitor(client, app)
    first = create_routed(client, headers, app)
    second = create_routed(client, headers, app)
    third = create_routed(client, headers, app)
    create_routed(client, headers, app)
    fourth = submit(client, headers, key="p1-" + uuid4().hex).json()[
        "ticket_id"
    ]  # team NULL is never exposed
    now = utcnow()
    with app.state.session_factory.begin() as s:
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.ticket_id == first)
            .values(
                status="RUNNING",
                lease_token=str(uuid4()),
                lease_owner="PRIVATE_WORKER",
                lease_until=now - timedelta(minutes=1),
                automation_generation=1,
            )
        )
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.ticket_id == second)
            .values(status="FAILED", error_code="PRIVATE_CONNECTION_TOKEN")
        )
        s.execute(tickets.update().where(tickets.c.ticket_id == third).values(version=99))
        s.execute(automation_control.update().values(generation=2))
    r = client.get(BASE + "/monitoring/summary", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["jobs"]["raw_counts"]["AUTO"]["PENDING"] == 2
    assert body["jobs"]["expired_running"] == 1
    assert body["jobs"]["generation_mismatch"] == 2  # expired and current pending overlap
    assert body["jobs"]["superseded"] == 1
    assert body["jobs"]["current_failed"] == 1
    assert body["automation"]["reason"] == "PERMISSION_REQUIRED"
    assert body["automation"]["state"] is None
    assert body["ai"]["attempts"] is None and body["ai"]["availability"] == "UNOBSERVED"
    assert body["analytics"]["reason"] == "NO_PUBLISHED_BATCH"
    page = client.get(BASE + "/monitoring/jobs", headers=h, params={"limit": 2}).json()
    second_page = client.get(
        BASE + "/monitoring/jobs", headers=h, params={"limit": 2, "cursor": page["next_cursor"]}
    ).json()
    all_rows = page["items"] + second_page["items"]
    assert len({r["job_id"] for r in all_rows}) == 4
    assert fourth not in {r["ticket_id"] for r in all_rows}
    assert next(r for r in all_rows if r["ticket_id"] == second)["error_code"] == "UNKNOWN_ERROR"
    assert "PRIVATE" not in str(all_rows)
    assert not {"lease_token", "lease_owner", "body", "customer_id"} & set(all_rows[0])
    assert client.get(BASE + "/monitoring/jobs", headers=h, params={"cursor": "bad"}).status_code == 422


def test_read_control_permission_and_missing_control(client, app):
    h = monitor(client, app, "AUTOMATION_READ")
    r = client.get(BASE + "/monitoring/summary", headers=h)
    assert r.json()["automation"]["state"]["revision"] == 1
    with app.state.session_factory.begin() as s:
        s.execute(automation_control.delete())
    body = client.get(BASE + "/monitoring/summary", headers=h).json()
    assert body["automation"]["reason"] == "AUTOMATION_CONTROL_UNAVAILABLE"
    assert body["jobs"]["generation_mismatch"] is None


def test_synthetic_batch_is_not_fabric_health(client, app):
    h = monitor(client, app)
    publish(client, app)
    body = client.get(BASE + "/monitoring/summary", headers=h).json()
    assert body["analytics"]["meta"]["source"] == "LOCAL_SYNTHETIC"
    assert body["analytics"]["connection_status"] == "UNOBSERVED"
    assert body["analytics"]["meta"]["origin_verification"] == "SERVICE_DECLARED_NOT_INDEPENDENTLY_VERIFIED"
    assert body["analytics"]["meta"]["stale"]


def test_ai_window_validation_and_revoked_account(client, app):
    h = monitor(client, app)
    for params in (
        {"from": "2026-11-01T00:00:00"},
        {"from": "2026-10-01T00:00:00Z", "to": "2026-11-01T00:00:00Z"},
        {"from": "2026-11-02T00:00:00Z", "to": "2026-11-01T00:00:00Z"},
    ):
        assert client.get(BASE + "/monitoring/ai-calls", headers=h, params=params).status_code == 422
    body = client.get(BASE + "/monitoring/ai-calls", headers=h).json()
    assert body["error_rate"] is None and body["sources"] == {"MOCK": None, "AZURE_OPENAI": None}
    with app.state.session_factory.begin() as s:
        s.execute(users.update().where(users.c.user_id == stable_id("admin")).values(active=False))
    assert client.get(BASE + "/monitoring/summary", headers=h).status_code == 401


def test_gets_do_not_mutate_jobs_or_control(client, headers, app):
    h = monitor(client, app)
    create_routed(client, headers, app)
    with app.state.session_factory() as s:
        before = [dict(r) for r in s.execute(select(automation_jobs)).mappings()]
    for path in ("/monitoring/summary", "/monitoring/jobs", "/monitoring/ai-calls"):
        assert client.get(BASE + path, headers=h).status_code == 200
    with app.state.session_factory() as s:
        assert [dict(r) for r in s.execute(select(automation_jobs)).mappings()] == before
        assert s.scalar(select(automation_control.c.revision)) == 1


def test_default_scope_excludes_other_team_and_job_filters(client, headers, app):
    h = monitor(client, app)
    visible = create_routed(client, headers, app)
    outside = create_routed(client, headers, app)
    with app.state.session_factory.begin() as s:
        s.execute(
            teams.insert().values(
                team_id=stable_id("outside-team"), name="outside", supported_categories=[], active=True
            )
        )
        s.execute(
            tickets.update().where(tickets.c.ticket_id == outside).values(team_id=stable_id("outside-team"))
        )
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.ticket_id == visible)
            .values(status="RETRY", next_attempt_at=utcnow() + timedelta(hours=1))
        )
    body = client.get(BASE + "/monitoring/summary", headers=h).json()
    assert body["jobs"]["raw_counts"]["AUTO"]["PENDING"] == 0
    assert body["jobs"]["retry_wait"] == 1
    rows = client.get(
        BASE + "/monitoring/jobs", headers=h, params={"status": "RETRY", "job_kind": "AUTO"}
    ).json()["items"]
    assert [r["ticket_id"] for r in rows] == [visible]
    assert (
        client.get(BASE + "/monitoring/jobs", headers=h, params={"job_kind": "HANDOFF"}).json()["items"] == []
    )
    for params in ({"status": "FAKE"}, {"job_kind": "P1"}, {"limit": 0}):
        assert client.get(BASE + "/monitoring/jobs", headers=h, params=params).status_code == 422


@pytest.mark.postgres
def test_summary_is_repeatable_read_during_job_change(client, headers, app, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from app.extensions.p1 import monitoring_service
    from tests.test_finalization_contract import require_postgres

    require_postgres(app)
    h = monitor(client, app)
    tid = create_routed(client, headers, app)
    entered, release = Event(), Event()
    original = monitoring_service.capabilities

    def paused(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)

    monkeypatch.setattr(monitoring_service, "capabilities", paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.get, BASE + "/monitoring/summary", headers=h)
        try:
            assert entered.wait(5)
            with app.state.session_factory.begin() as s:
                s.execute(
                    automation_jobs.update().where(automation_jobs.c.ticket_id == tid).values(status="FAILED")
                )
        finally:
            release.set()
        before = future.result(timeout=10).json()
    assert before["jobs"]["raw_counts"]["AUTO"]["PENDING"] == 1
    assert before["jobs"]["current_failed"] == 0
    monkeypatch.setattr(monitoring_service, "capabilities", original)
    assert client.get(BASE + "/monitoring/summary", headers=h).json()["jobs"]["current_failed"] == 1


def test_p1_permission_revocation_preserves_workload_capability(client, app):
    from app.staff_models import staff_permissions

    h = monitor(client, app, "WORKLOAD_READ")
    assert client.get(BASE + "/monitoring/summary", headers=h).status_code == 200
    assert client.get("/api/v1/staff/capabilities", headers=h).json()["capabilities"] == ["WORKLOAD_READ"]
    with app.state.session_factory.begin() as s:
        s.execute(
            staff_permissions.delete().where(
                staff_permissions.c.user_id == stable_id("admin"),
                staff_permissions.c.permission == "P1_MONITOR_READ",
            )
        )
    assert client.get(BASE + "/monitoring/summary", headers=h).status_code == 403
    assert client.get("/api/v1/staff/workload", headers=h).status_code == 200


def test_enabled_routes_require_bearer_and_include_response_guards(client):
    for path in ("/session", "/monitoring/summary", "/monitoring/jobs", "/monitoring/ai-calls"):
        response = client.get(BASE + path)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-request-id"]


def test_readiness_rejects_pre_p1_schema(client, app):
    from sqlalchemy import text

    with app.state.session_factory.begin() as s:
        s.execute(text("UPDATE alembic_version SET version_num='0007'"))
    assert client.get("/health/ready").status_code == 503
