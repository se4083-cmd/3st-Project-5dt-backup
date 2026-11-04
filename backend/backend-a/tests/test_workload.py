"""Workload authorization, distinct facts, deadline boundaries and bounded queries."""

import base64
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import delete, event, literal, select

from app import dependencies, workload
from app.db import UTCDateTime
from app.model_constraints import user_team_scopes
from app.models import assignments, automation_jobs, followup_actions, teams, tickets, users
from app.seed import stable_id
from app.staff_models import queue_routes
from tests.conftest import login_as
from tests.phase3_helpers import staff_user
from tests.phase6_helpers import grant

URL = "/api/v1/staff/workload"
NOW = datetime(2026, 11, 4, 3, tzinfo=timezone.utc)


@pytest.fixture
def clock(app):
    original = dependencies.get_snapshot_session

    def fixed(request: Request):
        with contextmanager(original)(request) as session:
            session.info["snapshot_as_of"] = NOW
            yield session

    app.dependency_overrides[original] = fixed
    yield
    app.dependency_overrides.pop(original, None)


def ticket(
    app,
    *,
    agent="agent",
    status="IN_PROGRESS",
    category="DELIVERY",
    team="team",
    due=None,
    cycle=1,
    assignment_cycle=None,
    routed=True,
    assigned=True,
    failed=False,
):
    tid = str(uuid4())
    with app.state.session_factory.begin() as s:
        s.execute(
            tickets.insert().values(
                ticket_id=tid,
                customer_id=stable_id("customer1/profile"),
                team_id=stable_id(team),
                category=category,
                status=status,
                cycle_no=cycle,
                sla_due_at=due if due is not None else NOW + timedelta(days=1),
                created_at=NOW - timedelta(days=1),
                resolved_at=NOW if status == "RESOLVED" else None,
                resolution_mode="HUMAN" if status == "RESOLVED" else None,
            )
        )
        if assigned:
            s.execute(
                assignments.insert().values(
                    assignment_id=str(uuid4()),
                    ticket_id=tid,
                    cycle_no=assignment_cycle or cycle,
                    team_id=stable_id(team),
                    agent_id=stable_id(agent),
                    assigned_at=NOW - timedelta(hours=1),
                    reason_code="LOCAL_TEST_ONLY",
                )
            )
        if routed:
            s.execute(
                queue_routes.insert().values(
                    ticket_id=tid,
                    cycle_no=cycle,
                    team_id=stable_id(team),
                    revision=1,
                    recorded_by_service="local-workload-test",
                )
            )
        if failed:
            s.execute(
                automation_jobs.insert().values(
                    job_id=str(uuid4()),
                    ticket_id=tid,
                    cycle_no=cycle,
                    expected_ticket_version=1,
                    status="FAILED",
                )
            )
    return tid


def followup(app, tid=None, *, owner="agent", due=None, responsibility=1, status="OPEN", team="team"):
    aid = str(uuid4())
    with app.state.session_factory.begin() as s:
        s.execute(
            followup_actions.insert().values(
                action_id=aid,
                ticket_id=tid,
                product_id=None if tid else stable_id("product"),
                cycle_no=1 if tid else None,
                responsibility_cycle_no=responsibility if tid else None,
                owner_team_id=stable_id(team),
                owner_user_id=stable_id(owner) if owner else None,
                kind="LOCAL_TEST",
                blocks_resolution=False,
                status=status,
                due_at=due,
                version=1,
                internal_note="PRIVATE_NOTE_SECRET",
                public_note="PRIVATE_PUBLIC_NOTE",
                created_at=NOW - timedelta(days=1),
                completed_at=NOW if status == "DONE" else None,
            )
        )
    return aid


def get(client, h, **params):
    response = client.get(URL, headers=h, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def admin(client, app):
    grant(app, "admin", "WORKLOAD_READ")
    return login_as(client, "admin")


def test_role_capability_scope_and_no_identity_or_count_leak(client, app, headers, clock):
    assert client.get(URL, headers=headers).status_code == 403
    ah = login_as(client, "admin")
    assert client.get(URL, headers=ah).status_code == 403
    h = admin(client, app)
    assert "WORKLOAD_READ" in client.get("/api/v1/staff/capabilities", headers=h).json()["capabilities"]
    other = staff_user(app, "outside", team_id=stable_id("outside-team"))
    for aid in (other, str(uuid4())):
        r = client.get(URL, headers=h, params={"agent_id": aid})
        assert r.status_code == 404
        assert set(r.json()) == {"error"}
        assert r.json()["error"]["code"] == "WORKLOAD_AGENT_NOT_FOUND"
    for team_id in (stable_id("outside-team"), str(uuid4())):
        assert client.get(URL, headers=h, params={"team_id": team_id}).status_code == 403
    gh = login_as(client, "agent")
    for aid in (other, str(uuid4())):
        assert client.get(URL, headers=gh, params={"agent_id": aid}).status_code == 403
    assert client.get(URL, headers=gh, params={"team_id": stable_id("outside-team")}).status_code == 403
    # Even a stray ADMIN-only grant does not broaden the AGENT role.
    grant(app, "agent", "WORKLOAD_READ", "UNROUTED_QUEUE_READ")
    assert "WORKLOAD_READ" not in client.get("/api/v1/staff/capabilities", headers=gh).json()["capabilities"]
    assert client.get(URL, headers=gh, params={"include_unrouted": True}).status_code == 403
    result = get(client, gh)
    assert result["view"] == "SELF" and result["team_queue"] is None and result["unrouted"] is None
    assert [x["agent_id"] for x in result["items"]] == [stable_id("agent")]


def test_distinct_current_cycle_waiting_category_and_failed_assigned(client, app, clock):
    h = admin(client, app)
    tid = ticket(app, status="WAITING_CUSTOMER", failed=True)
    with app.state.session_factory.begin() as s:
        for cycle in (1, 1, 2):
            s.execute(
                assignments.insert().values(
                    assignment_id=str(uuid4()),
                    ticket_id=tid,
                    cycle_no=cycle,
                    team_id=stable_id("team"),
                    agent_id=stable_id("agent"),
                    assigned_at=NOW - timedelta(days=2),
                    ended_at=NOW - timedelta(days=1),
                    reason_code="HISTORICAL_DUPLICATE",
                )
            )
    ticket(app, status="RESOLVED")
    ticket(app, status="CANCELLED")
    ticket(app, cycle=2, assignment_cycle=1)
    # Same workflow type is counted once even with multiple historical rows.
    result = get(client, h)
    counts = result["scope_totals"]["tickets"]
    assert counts["total"] == 1 and counts["waiting_customer"] == 1
    assert counts["by_category"] == {"DELIVERY": 1}
    assert result["team_queue"]["unassigned"]["total"] == 1
    assert result["team_queue"]["unassigned"]["invalid_assignment_count"] == 1
    assert result["scope_totals"] == result["page_totals"]


@pytest.mark.parametrize(
    "invalid", ["inactive_agent", "revoked_scope", "category", "inactive_team", "future_assignment"]
)
def test_invalid_assignment_is_subset_of_unassigned(client, app, clock, invalid):
    h = admin(client, app)
    tid = ticket(app)
    with app.state.session_factory.begin() as s:
        if invalid == "inactive_agent":
            s.execute(users.update().where(users.c.user_id == stable_id("agent")).values(active=False))
        elif invalid == "revoked_scope":
            s.execute(delete(user_team_scopes).where(user_team_scopes.c.user_id == stable_id("agent")))
        elif invalid == "category":
            s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(category="REFUND"))
        elif invalid == "inactive_team":
            s.execute(teams.update().where(teams.c.team_id == stable_id("team")).values(active=False))
        else:
            s.execute(
                assignments.update()
                .where(assignments.c.ticket_id == tid)
                .values(assigned_at=NOW + timedelta(seconds=1))
            )
    r = get(client, h)
    assert r["scope_totals"]["tickets"]["total"] == 0
    if invalid == "inactive_team":
        # Team is no longer authorized; neither its IDs nor its counts leak.
        assert r["team_ids"] == [] and r["items"] == []
        assert r["team_queue"]["unassigned"]["total"] == 0
    else:
        assert r["team_queue"]["unassigned"]["total"] == 1
        assert r["team_queue"]["unassigned"]["invalid_assignment_count"] == 1


def test_deadline_boundaries_null_and_no_mutation(client, app, clock):
    h = admin(client, app)
    for offset in (-1, 0, 7200, 7201):
        ticket(app, due=NOW + timedelta(seconds=offset))
    tid = ticket(app)
    for offset in (-1, 0, 7200, 7201, None):
        followup(app, tid, due=None if offset is None else NOW + timedelta(seconds=offset))
    with app.state.session_factory() as s:
        before = [
            tuple(x) for x in s.execute(select(tickets.c.ticket_id, tickets.c.sla_due_at, tickets.c.version))
        ]
        assert (
            s.scalar(select(workload.deadline_state(literal(None, type_=UTCDateTime()), NOW)))
            == "no_due_date"
        )
    r = get(client, h)
    assert r["as_of"] == "2026-11-04T03:00:00Z"
    assert r["scope_totals"]["tickets"] == {
        "total": 5,
        "overdue": 1,
        "due_soon": 2,
        "on_time": 2,
        "no_due_date": 0,
        "waiting_customer": 0,
        "by_category": {"DELIVERY": 5},
    }
    assert r["scope_totals"]["followups"] == {
        "total": 5,
        "overdue": 1,
        "due_soon": 2,
        "on_time": 1,
        "no_due_date": 1,
    }
    with app.state.session_factory() as s:
        assert before == [
            tuple(x) for x in s.execute(select(tickets.c.ticket_id, tickets.c.sla_due_at, tickets.c.version))
        ]


def test_unrouted_and_route_scope_are_separate_from_assigned_team(client, app, clock):
    h = admin(client, app)
    staff_user(app, "outside", team_id=stable_id("outside-team"))
    ticket(app, assigned=False)
    ticket(app, assigned=False, routed=False)
    ticket(app, assigned=False, team="outside-team")
    ticket(app, assigned=False, team="outside-team", routed=False)
    r = get(client, h)
    assert r["team_queue"]["unassigned"]["total"] == 1 and r["unrouted"] is None
    assert client.get(URL, headers=h, params={"include_unrouted": True}).status_code == 403
    grant(app, "admin", "UNROUTED_QUEUE_READ")
    r = get(client, h, include_unrouted=True)
    assert r["team_queue"]["unassigned"]["total"] == 1
    assert r["unrouted"]["total"] == 2
    assert r["unrouted"]["invalid_assignment_count"] == 0


def test_followup_ownership_handover_and_admin_product_queue(client, app, clock):
    h = admin(client, app)
    tid = ticket(app, cycle=2)
    followup(app, tid, responsibility=2)
    followup(app, tid, responsibility=1)
    followup(app, tid, responsibility=2, owner=None)
    followup(app, owner="admin", due=NOW - timedelta(seconds=1))
    followup(app, owner="agent")  # Product cannot be owned by an AGENT.
    followup(app, tid, responsibility=2, status="DONE")
    r = get(client, h)
    assert r["scope_totals"]["followups"]["total"] == 1
    assert r["items"][0]["followups"]["total"] == 1
    assert r["team_queue"]["waiting_followups"]["total"] == 3
    assert r["team_queue"]["admin_owned_followups"]["overdue"] == 1
    assert get(client, login_as(client, "agent"))["scope_totals"]["followups"]["total"] == 1
    with app.state.session_factory.begin() as s:
        s.execute(delete(user_team_scopes).where(user_team_scopes.c.user_id == stable_id("agent")))
    r = get(client, h)
    assert r["scope_totals"]["followups"]["total"] == 0
    assert r["team_queue"]["waiting_followups"]["total"] == 4


def test_pagination_scope_totals_filters_empty_and_private_allowlist(client, app, clock):
    h = admin(client, app)
    for i in range(4):
        staff_user(app, f"page-agent-{i}")
        ticket(app, agent=f"page-agent-{i}")
    pages = []
    cursor = None
    while True:
        p = get(client, h, limit=2, **({"cursor": cursor} if cursor else {}))
        assert p["total_agents"] == 5 and p["matching_agents"] == 5
        assert p["scope_totals"]["tickets"]["total"] == 4
        assert p["page_totals"]["tickets"]["total"] == sum(x["tickets"]["total"] for x in p["items"])
        pages.extend(x["agent_id"] for x in p["items"])
        cursor = p["next_cursor"]
        if not cursor:
            break
    assert pages == sorted(set(pages)) and len(pages) == 5
    p = get(client, h, agent_id=stable_id("page-agent-0"))
    assert p["matching_agents"] == 1 and p["total_agents"] == 5
    assert p["page_totals"]["tickets"]["total"] == 1 and p["scope_totals"]["tickets"]["total"] == 4
    assert set(p["items"][0]) == {"agent_id", "team_id", "tickets", "followups"}
    encoded = __import__("json").dumps(p)
    for forbidden in (
        "PRIVATE_",
        "customer_id",
        "ticket_id",
        "order_id",
        "body",
        "login_name",
        "internal_note",
    ):
        assert forbidden not in encoded
    assert client.get(URL, headers=h, params={"limit": 101}).status_code == 422
    assert client.get(URL, headers=h, params={"cursor": "bad"}).status_code == 422
    first = get(client, h, limit=1)
    assert (
        client.get(
            URL, headers=h, params={"cursor": first["next_cursor"], "agent_id": stable_id("agent")}
        ).status_code
        == 422
    )
    with app.state.session_factory.begin() as s:
        s.execute(delete(user_team_scopes).where(user_team_scopes.c.user_id == stable_id("admin")))
    p = get(client, h)
    assert p["items"] == [] and p["total_agents"] == 0 and p["scope_totals"]["tickets"]["total"] == 0


def test_query_count_is_independent_of_page_size(client, app, clock):
    h = admin(client, app)
    for i in range(5):
        staff_user(app, f"query-agent-{i}")
    queries = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            queries.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", capture)
    try:
        get(client, h, limit=1)
        small = len(queries)
        queries.clear()
        get(client, h, limit=100)
        large = len(queries)
    finally:
        event.remove(app.state.engine, "before_cursor_execute", capture)
    assert small == large and large <= 12


def test_unknown_type_is_counted_without_echoing_text(client, app, clock):
    h = admin(client, app)
    ticket(app, assigned=False, category="PRIVATE_FREE_TEXT")
    r = get(client, h)
    assert r["team_queue"]["unassigned"]["by_category"] == {"UNCLASSIFIED": 1}


@pytest.mark.parametrize("invalid", ["inactive_owner", "category_mismatch"])
def test_invalid_followup_owner_remains_in_team_waiting(client, app, clock, invalid):
    h = admin(client, app)
    tid = ticket(app)
    followup(app, tid)
    with app.state.session_factory.begin() as s:
        if invalid == "inactive_owner":
            s.execute(users.update().where(users.c.user_id == stable_id("agent")).values(active=False))
        else:
            s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(category="REFUND"))
    r = get(client, h)
    assert r["scope_totals"]["followups"]["total"] == 0
    assert r["team_queue"]["waiting_followups"]["total"] == 1


def test_cursor_type_scope_change_and_server_time_only(client, app, clock):
    h = admin(client, app)
    staff_user(app, "cursor-agent")
    first = get(client, h, limit=1, as_of="1900-01-01T00:00:00Z")
    assert first["as_of"] == "2026-11-04T03:00:00Z"
    cursor = first["next_cursor"]
    values = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    malformed = base64.urlsafe_b64encode(json.dumps([values[0], 123]).encode()).decode()
    assert client.get(URL, headers=h, params={"cursor": malformed}).status_code == 422
    with app.state.session_factory.begin() as s:
        s.execute(delete(user_team_scopes).where(user_team_scopes.c.user_id == stable_id("admin")))
    assert client.get(URL, headers=h, params={"cursor": cursor}).status_code == 422
