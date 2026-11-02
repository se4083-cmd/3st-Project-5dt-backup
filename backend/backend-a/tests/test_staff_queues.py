import pytest
from sqlalchemy import select

from app import audit
from app.errors import APIError
from app.exception_queue import RouteCommand, record_queue_route
from app.models import automation_jobs, tickets
from app.seed import stable_id
from app.staff_models import queue_routes
from tests.conftest import login_as
from tests.phase3_helpers import assign, staff_user
from tests.phase6_helpers import BASE, grant, route
from tests.test_flow import submit
from tests.test_ticket_commands import action


@pytest.mark.parametrize("role", ["customer1", "agent", "admin"])
def test_no_implicit_queue_or_unrouted_permission(client, headers, app, role):
    submit(client, headers)
    h = login_as(client, role)
    for query in ({}, {"queue_scope": "UNROUTED"}):
        for suffix in ("", "/counts"):
            assert client.get(BASE + "/exception-queue" + suffix, headers=h, params=query).status_code == 403


def test_routed_queue_does_not_grant_detail_or_customer360(client, headers, app):
    tid = submit(client, headers).json()["ticket_id"]
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(category="DELIVERY"))
    route(app, tid)
    grant(app, "agent", "EXCEPTION_QUEUE_READ")
    h = login_as(client, "agent")
    page = client.get(BASE + "/exception-queue", headers=h).json()
    assert page["total"] == 1 and page["items"][0]["ticket_id"] == tid
    assert set(page["items"][0]) == {
        "ticket_id",
        "cycle_no",
        "route_team_id",
        "reason_code",
        "stage",
        "queued_at",
        "waiting_seconds",
        "job_state",
        "automatic_state",
    }
    assert client.get("/api/v1/tickets/" + tid, headers=h).status_code == 404
    assert (
        client.post(
            BASE + f"/tickets/{tid}/internal", headers=h, json={"purpose_code": "ACTIVE_SUPPORT"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            BASE + f"/customers/{stable_id('customer1/profile')}/360",
            headers=h,
            json={"purpose_code": "ACTIVE_SUPPORT"},
        ).status_code
        == 404
    )


def test_unrouted_requires_explicit_global_capability_and_minimum_dto(client, headers, app):
    tid = submit(client, headers).json()["ticket_id"]
    grant(app, "admin", "EXCEPTION_QUEUE_READ")
    h = login_as(client, "admin")
    assert client.get(BASE + "/exception-queue", headers=h).json()["total"] == 0
    assert (
        client.get(BASE + "/exception-queue", params={"queue_scope": "UNROUTED"}, headers=h).status_code
        == 403
    )
    grant(app, "admin", "UNROUTED_QUEUE_READ")
    r = client.get(BASE + "/exception-queue", params={"queue_scope": "UNROUTED"}, headers=h).json()
    assert r["total"] == 1 and r["items"][0]["route_team_id"] is None
    assert (
        client.post(
            BASE + f"/tickets/{tid}/internal", headers=h, json={"purpose_code": "QUALITY_REVIEW"}
        ).status_code
        == 404
    )
    grant(app, "agent", "UNROUTED_QUEUE_READ")
    assert (
        client.get(
            BASE + "/exception-queue", params={"queue_scope": "UNROUTED"}, headers=login_as(client, "agent")
        ).status_code
        == 403
    )


def test_queue_counts_filters_cursor_and_cross_team_match(client, headers, app):
    grant(app, "admin", "EXCEPTION_QUEUE_READ")
    ids = []
    for n in range(4):
        tid = submit(client, headers, key=f"queue-page-{n}").json()["ticket_id"]
        route(app, tid)
        ids.append(tid)
    other_team = stable_id("queue-other-team")
    staff_user(app, "queue-other", team_id=other_team)
    hidden = submit(client, headers, key="queue-hidden-team").json()["ticket_id"]
    route(app, hidden, team="queue-other-team")
    with app.state.session_factory.begin() as s:
        s.execute(
            automation_jobs.update().where(automation_jobs.c.ticket_id == ids[0]).values(status="FAILED")
        )
    h = login_as(client, "admin")
    page = client.get(BASE + "/exception-queue", headers=h, params={"limit": 2}).json()
    counts = client.get(BASE + "/exception-queue/counts", headers=h).json()
    assert page["total"] == counts["total"] == 4 and page["counts"] == counts["counts"]
    second = client.get(
        BASE + "/exception-queue", headers=h, params={"limit": 2, "cursor": page["next_cursor"]}
    ).json()
    assert {r["ticket_id"] for r in page["items"] + second["items"]} == set(ids)
    f = {"reason": "AUTO_FAILED"}
    assert client.get(BASE + "/exception-queue", headers=h, params=f).json()["total"] == 1
    assert client.get(BASE + "/exception-queue/counts", headers=h, params=f).json()["total"] == 1
    assert client.get(BASE + "/exception-queue", headers=h, params={"team_id": other_team}).status_code == 403


def test_old_route_and_ended_assignment_do_not_restore_scope(client, headers, app):
    tid = submit(client, headers).json()["ticket_id"]
    route(app, tid)
    assign(app, tid)
    grant(app, "agent", "EXCEPTION_QUEUE_READ")
    h = login_as(client, "agent")
    assert client.get(BASE + "/exception-queue", headers=h).json()["total"] == 0
    assert action(client, headers, tid).status_code == 201
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(category="DELIVERY"))
    assert client.get(BASE + "/exception-queue", headers=h).json()["total"] == 0
    route(app, tid)
    assert client.get(BASE + "/exception-queue", headers=h).json()["total"] == 1
    assert (
        client.post(
            BASE + f"/tickets/{tid}/internal", headers=h, json={"purpose_code": "ACTIVE_SUPPORT"}
        ).status_code
        == 404
    )
    with app.state.session_factory() as s:
        assert len(s.execute(select(queue_routes).where(queue_routes.c.ticket_id == tid)).all()) == 2


def test_route_revision_and_atomic_audit_rollback(client, headers, app, monkeypatch):
    tid = submit(client, headers).json()["ticket_id"]
    first = route(app, tid)
    assert first["revision"] == 1
    with pytest.raises(APIError), app.state.session_factory.begin() as s:
        record_queue_route(
            s,
            tid,
            RouteCommand(expected_revision=1, cycle_no=1, expected_route_revision=0, team_id=None),
            service_id="local-fixture",
        )
    original = audit.record

    def fail(*args, **kwargs):
        if args[2] == "QUEUE_ROUTE_RECORDED":
            raise RuntimeError("injected")
        return original(*args, **kwargs)

    monkeypatch.setattr(audit, "record", fail)
    with pytest.raises(RuntimeError):
        route(app, tid, expected_route_revision=1, team=None)
    with app.state.session_factory() as s:
        r = s.execute(select(queue_routes)).mappings().one()
        assert r["revision"] == 1 and r["team_id"] == stable_id("team")


def test_human_request_and_failure_reasons_are_not_raw_error_text(client, headers, app):
    tid = submit(client, headers).json()["ticket_id"]
    assert action(client, headers, tid, "request-agent").status_code == 201
    route(app, tid)
    grant(app, "admin", "EXCEPTION_QUEUE_READ")
    h = login_as(client, "admin")
    assert (
        client.get(BASE + "/exception-queue", headers=h).json()["items"][0]["reason_code"] == "HUMAN_REQUEST"
    )
    with app.state.session_factory.begin() as s:
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.ticket_id == tid, automation_jobs.c.cycle_no == 2)
            .values(status="FAILED", error_code="PRIVATE_ERROR_TOKEN")
        )
    response = client.get(BASE + "/exception-queue", headers=h)
    assert (
        response.json()["items"][0]["reason_code"] == "ROUTING_FAILED"
        and "PRIVATE_ERROR" not in response.text
    )


def test_inactive_route_is_quarantined_only_for_explicit_global_admin(client, headers, app):
    from app.models import teams

    tid = submit(client, headers).json()["ticket_id"]
    route(app, tid)
    grant(app, "admin", "EXCEPTION_QUEUE_READ")
    with app.state.session_factory.begin() as s:
        s.execute(teams.update().where(teams.c.team_id == stable_id("team")).values(active=False))
    h = login_as(client, "admin")
    assert client.get(BASE + "/exception-queue", headers=h).json()["total"] == 0
    assert (
        client.get(BASE + "/exception-queue", headers=h, params={"queue_scope": "UNROUTED"}).status_code
        == 403
    )
    grant(app, "admin", "UNROUTED_QUEUE_READ")
    page = client.get(BASE + "/exception-queue", headers=h, params={"queue_scope": "UNROUTED"}).json()
    assert page["total"] == 1 and page["items"][0]["route_team_id"] is None


def test_effective_capabilities_are_separate_from_role_and_team_count(client, headers, app):
    from app.model_constraints import user_team_scopes

    staff_user(app, "extra-scope", team_id=stable_id("extra-scope-team"))
    with app.state.session_factory.begin() as s:
        s.execute(
            user_team_scopes.insert().values(
                user_id=stable_id("admin"), team_id=stable_id("extra-scope-team")
            )
        )
    h = login_as(client, "admin")
    assert client.get(BASE + "/capabilities", headers=h).json()["capabilities"] == []
    assert (
        client.get(BASE + "/exception-queue", headers=h, params={"queue_scope": "UNROUTED"}).status_code
        == 403
    )
    grant(app, "admin", "AUTOMATION_READ")
    assert client.get(BASE + "/capabilities", headers=h).json()["capabilities"] == ["AUTOMATION_READ"]
