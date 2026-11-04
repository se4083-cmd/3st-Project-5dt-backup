"""Read-only recommendations with synthetic workflow rows, not a B engine."""

import base64
import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select, text

from app import recommendations
from app.model_constraints import team_categories, user_team_scopes
from app.models import assignments, automation_jobs, messages, teams, tickets, users
from app.seed import stable_id
from app.staff_models import queue_routes, staff_permissions
from tests.conftest import login_as
from tests.phase3_helpers import staff_user
from tests.test_workload import (
    NOW,
    followup,
    ticket,
)

URL = "/api/v1/staff/assignment-recommendations"
TEAM = stable_id("team")


@pytest.fixture(autouse=True)
def recommendation_clock(app):
    from tests.test_workload import clock

    yield from clock.__wrapped__(app)


def grant(app, label="admin", permission="ASSIGNMENT_RECOMMEND"):
    with app.state.session_factory.begin() as s:
        s.execute(staff_permissions.insert().values(user_id=stable_id(label), permission=permission))


def admin(client, app):
    grant(app)
    return login_as(client, "admin")


def pending(
    app,
    *,
    identifier=None,
    mode="HUMAN",
    status="HANDOFF_PENDING",
    due=None,
    category="DELIVERY",
    route_team=TEAM,
    cycle=1,
    route_cycle=None,
    failed=False,
):
    tid = identifier or str(uuid4())
    with app.state.session_factory.begin() as s:
        s.execute(
            tickets.insert().values(
                ticket_id=tid,
                customer_id=stable_id("customer1/profile"),
                requested_mode=mode,
                status=status,
                cycle_no=cycle,
                category=category,
                sla_due_at=due or NOW + timedelta(days=1),
                resolved_at=NOW if status == "RESOLVED" else None,
                resolution_mode="HUMAN" if status == "RESOLVED" else None,
            )
        )
        if route_team:
            s.execute(
                queue_routes.insert().values(
                    ticket_id=tid,
                    cycle_no=route_cycle or cycle,
                    team_id=route_team,
                    revision=2,
                    recorded_by_service="synthetic-recommend-test",
                    recorded_at=NOW - timedelta(days=10),
                )
            )
        if failed:
            s.execute(
                automation_jobs.insert().values(
                    job_id=str(uuid4()),
                    ticket_id=tid,
                    cycle_no=cycle,
                    expected_ticket_version=1,
                    job_kind="AUTO",
                    status="FAILED",
                )
            )
    return tid


def get(client, h, **params):
    r = client.get(URL, headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("label", ["customer1", "agent", "admin"])
def test_roles_and_explicit_capability(client, app, label):
    h = login_as(client, label)
    assert client.get(URL, headers=h).status_code == 403
    assert client.get(URL, headers=h, params={"ticket_id": str(uuid4())}).status_code == 403
    if label == "agent":
        grant(app, "agent")
        assert client.get(URL, headers=h).status_code == 403
        assert (
            "ASSIGNMENT_RECOMMEND"
            not in client.get("/api/v1/staff/capabilities", headers=h).json()["capabilities"]
        )


def test_human_only_failed_auto_preserved_and_no_business_writes(client, app):
    h = admin(client, app)
    human = pending(app, failed=True)
    auto = pending(app, mode="AUTO", status="PROCESSING")
    closed = pending(app, status="RESOLVED")
    with app.state.session_factory.begin() as s:
        # A preserved FAILED AUTO job may fence an earlier revision. This reader
        # reports current ticket revision without changing or reviving that job.
        s.execute(tickets.update().where(tickets.c.ticket_id == human).values(version=2))
        s.execute(
            messages.insert().values(
                message_id=str(uuid4()),
                ticket_id=human,
                cycle_no=1,
                role="CUSTOMER",
                direction="IN",
                body="PRIVATE_CUSTOMER_TEXT",
                visibility="PUBLIC",
            )
        )
    tables = [tickets, automation_jobs, assignments, queue_routes]
    with app.state.session_factory() as s:
        before = {t.name: list(s.execute(select(t).order_by(*t.primary_key.columns))) for t in tables}
    d = get(client, h)
    assert [i["ticket_id"] for i in d["items"]] == [human]
    i = d["items"][0]
    assert i["ticket_revision"] == 2
    assert i["recommendation_state"] == "AVAILABLE" and i["route_revision"] == 2
    assert "FAILED_AUTO_HISTORY_PRESERVED" in i["reason_codes"]
    assert i["candidates"][0]["agent_id"] == stable_id("agent")
    assert i["waiting_since"] is None and i["route_recorded_at"] is not None
    assert i["waiting_basis"] == "NOT_RECORDED_NOT_INFERRED"
    assert "PRIVATE_CUSTOMER_TEXT" not in str(d) and "customer_id" not in str(d) and "order_id" not in str(d)
    assert "NOT_HUMAN_PATH" in get(client, h, ticket_id=auto)["items"][0]["reason_codes"]
    assert "STATE_NOT_ASSIGNABLE" in get(client, h, ticket_id=closed)["items"][0]["reason_codes"]
    with app.state.session_factory() as s:
        assert before == {t.name: list(s.execute(select(t).order_by(*t.primary_key.columns))) for t in tables}
    from datetime import datetime

    assert (
        datetime.fromisoformat(d["expires_at"].replace("Z", "+00:00"))
        - datetime.fromisoformat(d["as_of"].replace("Z", "+00:00"))
    ).total_seconds() == 30
    assert d["rule_version"] == "WORKLOAD_PRIORITY_V1"


def test_scope_revocation_outside_ids_and_unrouted(client, app):
    h = admin(client, app)
    other_team = stable_id("recommend-other-team")
    staff_user(app, "recommend-other-agent", team_id=other_team)
    other = pending(app, route_team=other_team)
    unrouted = pending(app, route_team=None)
    old_route = pending(app, cycle=2, route_cycle=1)
    assert client.get(URL, headers=h, params={"ticket_id": other}).status_code == 404
    assert client.get(URL, headers=h, params={"team_id": other_team}).status_code == 403
    for tid in [unrouted, old_route]:
        assert client.get(URL, headers=h, params={"ticket_id": tid}).status_code == 404
    grant(app, permission="UNROUTED_QUEUE_READ")
    for tid in [unrouted, old_route]:
        i = get(client, h, ticket_id=tid)["items"][0]
        assert (
            i["recommendation_state"] == "UNAVAILABLE"
            and i["candidates"] == []
            and i["route_team_id"] is None
        )
        assert "UNROUTED_NO_RECOMMENDATION" in i["reason_codes"]
    assert get(client, h)["items"] == []
    mine = pending(app)
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
    assert get(client, h)["items"] == []
    assert client.get(URL, headers=h, params={"ticket_id": mine}).status_code == 404


def test_valid_assignments_excluded_invalid_old_rows_conditional(client, app):
    h = admin(client, app)
    assigned = ticket(app, status="IN_PROGRESS", assigned=True)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == assigned).values(requested_mode="HUMAN"))
        s.execute(
            automation_jobs.insert().values(
                job_id=str(uuid4()),
                ticket_id=assigned,
                cycle_no=1,
                expected_ticket_version=1,
                job_kind="AUTO",
                status="FAILED",
            )
        )
    assert "ALREADY_VALIDLY_ASSIGNED" in get(client, h, ticket_id=assigned)["items"][0]["reason_codes"]
    tid = pending(app, cycle=2)
    with app.state.session_factory.begin() as s:
        s.execute(
            assignments.insert().values(
                assignment_id=str(uuid4()),
                ticket_id=tid,
                cycle_no=1,
                team_id=TEAM,
                agent_id=stable_id("agent"),
                assigned_at=NOW - timedelta(hours=1),
                reason_code="SYNTHETIC_OLD_CYCLE",
            )
        )
    i = get(client, h, ticket_id=tid)["items"][0]
    assert i["recommendation_state"] == "CONDITIONAL" and i["invalid_active_assignment_present"]
    assert "PHYSICAL_ASSIGNMENT_RECONCILIATION_REQUIRED" in i["reason_codes"]
    with app.state.session_factory.begin() as s:
        s.execute(assignments.update().where(assignments.c.ticket_id == tid).values(ended_at=NOW))
    assert get(client, h, ticket_id=tid)["items"][0]["recommendation_state"] == "AVAILABLE"


@pytest.mark.parametrize(
    "change", ["inactive_agent", "agent_scope", "category", "inactive_team", "not_agent", "unknown_category"]
)
def test_candidate_qualifications_and_missing_reasons(client, app, change):
    h = admin(client, app)
    tid = pending(app, category="UNCLASSIFIED" if change == "unknown_category" else "DELIVERY")
    with app.state.session_factory.begin() as s:
        if change == "inactive_agent":
            s.execute(users.update().where(users.c.user_id == stable_id("agent")).values(active=False))
        if change == "agent_scope":
            s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("agent")))
        if change == "category":
            s.execute(team_categories.delete().where(team_categories.c.team_id == TEAM))
        if change == "inactive_team":
            s.execute(teams.update().where(teams.c.team_id == TEAM).values(active=False))
        if change == "not_agent":
            s.execute(
                users.update().where(users.c.user_id == stable_id("agent")).values(role="ADMIN", team_id=None)
            )
    if change == "inactive_team":
        assert get(client, h)["items"] == []
        grant(app, permission="UNROUTED_QUEUE_READ")
    i = get(client, h, ticket_id=tid)["items"][0]
    assert i["candidates"] == [] and i["recommendation_state"] == "UNAVAILABLE"
    expected = (
        "CATEGORY_UNKNOWN"
        if change == "unknown_category"
        else "ROUTE_CATEGORY_UNSUPPORTED"
        if change == "category"
        else "UNROUTED_NO_RECOMMENDATION"
        if change == "inactive_team"
        else "NO_ELIGIBLE_AGENT"
    )
    assert expected in i["reason_codes"]


def test_load_primary_secondary_waiting_customer_and_followups_separate(client, app):
    h = admin(client, app)
    staff_user(app, "recommend-agent-b")
    ticket(app, due=NOW - timedelta(seconds=1))
    b = ticket(app, agent="recommend-agent-b", status="WAITING_CUSTOMER", due=NOW)
    followup(app, b, owner="recommend-agent-b", due=NOW - timedelta(days=1))
    tid = pending(app)
    people = get(client, h, ticket_id=tid)["items"][0]["candidates"]
    assert [p["agent_id"] for p in people] == [stable_id("recommend-agent-b"), stable_id("agent")]
    first = people[0]
    assert first["tickets"]["total"] == 1 and first["tickets"]["waiting_customer"] == 1
    assert first["followups"]["total"] == 1 and first["followups"]["overdue"] == 1
    assert first["tickets"]["overdue"] == 0
    ticket(app, agent="recommend-agent-b", due=NOW + timedelta(days=1))
    assert get(client, h, ticket_id=tid)["items"][0]["candidates"][0]["agent_id"] == stable_id("agent")


def test_deadline_boundaries_null_and_stable_pages(client, app):
    h = admin(client, app)
    ids = []
    for n, due in [
        (5, NOW + timedelta(hours=3)),
        (4, NOW + timedelta(hours=2)),
        (3, NOW),
        (2, NOW - timedelta(microseconds=1)),
        (6, NOW + timedelta(days=2)),
    ]:
        ids.append(pending(app, identifier=str(UUID(int=n)), due=due))
    if app.state.engine.dialect.name == "postgresql":
        # Defensive legacy NULL branch only: change this disposable test schema, never application DDL.
        with app.state.session_factory.begin() as s:
            s.execute(text("ALTER TABLE tickets ALTER COLUMN sla_due_at DROP NOT NULL"))
            s.execute(tickets.update().where(tickets.c.ticket_id == str(UUID(int=6))).values(sla_due_at=None))
    first = get(client, h, limit=2)
    second = get(client, h, limit=2, cursor=first["next_cursor"])
    third = get(client, h, limit=2, cursor=second["next_cursor"])
    items = first["items"] + second["items"] + third["items"]
    assert [x["ticket_id"] for x in items] == [str(UUID(int=n)) for n in [2, 3, 4, 5, 6]]
    assert [x["deadline_state"] for x in items[:4]] == ["overdue", "due_soon", "due_soon", "on_time"]
    if app.state.engine.dialect.name == "postgresql":
        assert items[-1]["deadline_state"] == "no_due_date"
    assert first["total"] == 5 and third["next_cursor"] is None
    assert (
        client.get(URL, headers=h, params={"cursor": first["next_cursor"], "candidate_limit": 2}).status_code
        == 422
    )
    decoded = json.loads(
        base64.urlsafe_b64decode(first["next_cursor"] + "=" * (-len(first["next_cursor"]) % 4))
    )
    decoded[2] = 42
    malformed = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode().rstrip("=")
    assert client.get(URL, headers=h, params={"cursor": malformed}).status_code == 422


def test_tie_order_candidate_limit_filters_and_payload(client, app):
    h = admin(client, app)
    for n in range(4):
        staff_user(app, f"recommend-tie-{n}")
    tid = pending(app)
    d = get(client, h, ticket_id=tid, candidate_limit=2)
    i = d["items"][0]
    expected = sorted([stable_id("agent")] + [stable_id(f"recommend-tie-{n}") for n in range(4)])
    assert [a["agent_id"] for a in i["candidates"]] == expected[:2]
    assert i["eligible_candidate_count"] == 5 and i["candidates_truncated"]
    for params in [{"limit": 51}, {"candidate_limit": 11}, {"ticket_id": tid, "cursor": "bogus"}]:
        assert client.get(URL, headers=h, params=params).status_code == 422
    response = client.get(URL, headers=h)
    assert response.headers["Cache-Control"] == "no-store"
    assert set(response.json()["items"][0]["candidates"][0]) == {
        "agent_id",
        "team_id",
        "tickets",
        "followups",
        "rank",
        "reason_codes",
    }


def test_same_snapshot_scope_assignment_and_loads(client, app, monkeypatch):
    h = admin(client, app)
    tid = pending(app)
    owned = ticket(app)
    original = recommendations.rank_candidates

    def concurrent_change(session, *args, **kw):
        assert session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        with app.state.session_factory.begin() as writer:
            writer.execute(assignments.update().where(assignments.c.ticket_id == owned).values(ended_at=NOW))
            writer.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
        return original(session, *args, **kw)

    monkeypatch.setattr(recommendations, "rank_candidates", concurrent_change)
    d = get(client, h, ticket_id=tid)
    assert d["items"][0]["candidates"][0]["tickets"]["total"] == 1
    monkeypatch.setattr(recommendations, "rank_candidates", original)
    assert get(client, h)["items"] == []


def test_bounded_queries_independent_hints_and_capability_revoked(client, app):
    h = admin(client, app)
    for _ in range(3):
        pending(app)
    statements = []

    def called(*args):
        statements.append(1)

    event.listen(app.state.engine, "before_cursor_execute", called)
    try:
        first = get(client, h, limit=1)
        n = len(statements)
        statements.clear()
        second = get(client, h, limit=3)
        assert len(statements) <= n + 1
        assert len(second["items"]) == 3
        assert all(
            i["candidates"][0]["agent_id"] == first["items"][0]["candidates"][0]["agent_id"]
            for i in second["items"]
        )
    finally:
        event.remove(app.state.engine, "before_cursor_execute", called)
    with app.state.session_factory.begin() as s:
        s.execute(
            staff_permissions.delete().where(
                staff_permissions.c.user_id == stable_id("admin"),
                staff_permissions.c.permission == "ASSIGNMENT_RECOMMEND",
            )
        )
    assert client.get(URL, headers=h).status_code == 403
