import json

import pytest
from sqlalchemy import select

from app import customer360
from app.db import utcnow
from app.model_constraints import user_team_scopes
from app.models import assignments, audit_events, tickets
from app.seed import stable_id
from tests.conftest import login_as
from tests.phase3_helpers import assign, create_followup, make_ticket, staff_user


def overview(client, auth, customer=None, purpose="ACTIVE_SUPPORT"):
    return client.post(
        f"/api/v1/staff/customers/{customer or stable_id('customer1/profile')}/360",
        headers=auth,
        json={"purpose_code": purpose},
    )


@pytest.fixture
def history(client, headers, app):
    team_b = stable_id("team-b")
    staff_user(app, "agent-b", team_id=team_b)
    staff_user(app, "admin-b", "ADMIN", team_b)
    active = [make_ticket(client, headers, app, key=f"history-active-{i}") for i in range(5)]
    assign(app, active[0], cycle=3)
    closed = make_ticket(client, headers, app, key="history-closed")
    assign(app, closed, status="RESOLVED", mode="AUTO")
    ended = make_ticket(client, headers, app, key="history-ended")
    with app.state.session_factory.begin() as session:
        session.execute(
            assignments.update().where(assignments.c.ticket_id == ended).values(ended_at=utcnow())
        )
    wrong_category = make_ticket(client, headers, app, key="history-category")
    with app.state.session_factory.begin() as session:
        session.execute(
            tickets.update().where(tickets.c.ticket_id == wrong_category).values(category="PAYMENT")
        )
    other = [make_ticket(client, headers, app, key=f"history-b-{i}") for i in range(2)]
    for tid in other:
        assign(app, tid, agent="agent-b", team_id=team_b)
    agent, admin, admin_b = [login_as(client, label) for label in ["agent", "admin", "admin-b"]]
    public_action = create_followup(client, agent, active[0]).json()["action_id"]
    private_action = create_followup(
        client,
        admin,
        closed,
        key="history-closed-followup",
        blocks_resolution=False,
        owner_user_id=stable_id("admin"),
        public_note=None,
    ).json()["action_id"]
    b_action = create_followup(
        client,
        admin_b,
        other[0],
        owner_team_id=team_b,
        owner_user_id=stable_id("agent-b"),
        internal_note="B_ONLY_PRIVATE_NOTE",
        key="history-b-followup",
    ).json()["action_id"]
    return dict(
        active=active,
        closed=closed,
        ended=ended,
        wrong_category=wrong_category,
        other=other,
        agent=agent,
        admin=admin,
        admin_b=admin_b,
        public_action=public_action,
        private_action=private_action,
        b_action=b_action,
    )


def test_customer360_uses_per_ticket_scope_for_every_collection(client, headers, app, history):
    h = history
    result = overview(client, h["agent"])
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["total_ticket_count"] == 5 and data["category_counts"] == {"DELIVERY": 5}
    assert data["handling_counts"] == {"AUTOMATED": 0, "HUMAN": 5}
    assert data["unresolved_ticket_count"] == 5
    assert data["reopened_ticket_count"] == 1 and data["additional_cycle_count"] == 2
    assert {t["ticket_id"] for t in data["recent_tickets"]} == set(h["active"])
    assert data["followup_count"] == 1
    assert data["followups"]["items"][0]["action_id"] == h["public_action"]
    assert all(t["current_assignment"] is not None for t in data["recent_tickets"])
    path = f"/api/v1/staff/customers/{stable_id('customer1/profile')}/360/tickets"
    seen, cursor = [], None
    while True:
        page = client.post(
            path,
            headers=h["agent"],
            json={"purpose_code": "ACTIVE_SUPPORT"},
            params={"limit": 2, **({"cursor": cursor} if cursor else {})},
        ).json()
        seen.extend(t["ticket_id"] for t in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 5 and set(seen) == set(h["active"])
    for tid in seen:
        assert client.get(f"/api/v1/tickets/{tid}", headers=h["agent"]).status_code == 200
    for tid in [h["closed"], h["ended"], h["wrong_category"], *h["other"]]:
        assert tid not in result.text
        assert client.get(f"/api/v1/tickets/{tid}", headers=h["agent"]).status_code == 404
    assert "B_ONLY_PRIVATE_NOTE" not in result.text
    assert overview(client, headers).status_code == 403
    assert overview(client, login_as(client, "customer2")).status_code == 403


def test_admin360_only_allowed_team_and_ignores_terminal_stale_assignment(client, app, history):
    h = history
    first = overview(client, h["admin"]).json()
    second = overview(client, h["admin_b"]).json()
    assert first["total_ticket_count"] == 8 and second["total_ticket_count"] == 2
    assert sum(first["category_counts"].values()) == 8
    assert first["followup_count"] == 2 and second["followup_count"] == 1
    assert "B_ONLY_PRIVATE_NOTE" not in json.dumps(first)
    page = client.post(
        f"/api/v1/staff/customers/{stable_id('customer1/profile')}/360/tickets",
        headers=h["admin"],
        json={"purpose_code": "QUALITY_REVIEW"},
        params={"limit": 100},
    ).json()
    closed = next(t for t in page["items"] if t["ticket_id"] == h["closed"])
    assert closed["current_assignment"] is None
    assert len(first["recent_tickets"]) == 5 and len(first["facts"]) == 3


def test_360_purpose_and_scope_are_independent_and_audited(client, headers, app):
    make_ticket(client, headers, app)
    agent = login_as(client, "agent")
    assert overview(client, agent, purpose="QUALITY_REVIEW").status_code == 403
    assert overview(client, agent, customer=stable_id("customer2/profile")).status_code == 404
    path = f"/api/v1/staff/customers/{stable_id('customer1/profile')}/360"
    assert client.post(path, headers=agent, json={}).status_code == 422
    assert (
        client.post(path, headers=agent, json={"purpose_code": "please show all customers"}).status_code
        == 422
    )
    assert overview(client, agent, purpose="FOLLOWUP_REVIEW").status_code == 200
    with app.state.session_factory() as session:
        event = (
            session.execute(select(audit_events).where(audit_events.c.action == "CUSTOMER360_READ"))
            .mappings()
            .one()
        )
        assert event["reason_code"] == "FOLLOWUP_REVIEW" and event["payload"] == {}


def test_summary_input_is_minimal_and_fingerprint_tracks_evidence_and_scope(client, headers, app):
    tid = make_ticket(client, headers, app)
    admin = login_as(client, "admin")
    aid = create_followup(client, admin, tid, owner_user_id=stable_id("admin")).json()["action_id"]
    first = overview(client, admin).json()
    assert (
        overview(client, admin).json()["summary_contract"]["cache_fingerprint"]
        == first["summary_contract"]["cache_fingerprint"]
    )
    external = first["summary_contract"]["external_input"]
    assert all(isinstance(v, int) for v in external.values())
    assert "PRIVATE" not in json.dumps(external) and "ticket_id" not in json.dumps(external)
    assert first["summary_contract"]["status"] == "NOT_GENERATED"
    patched = client.patch(
        f"/api/v1/staff/followups/{aid}",
        headers=admin,
        json={"expected_revision": 1, "internal_note": "Updated private evidence"},
    )
    assert patched.status_code == 200
    second = overview(client, admin).json()["summary_contract"]["cache_fingerprint"]
    assert second != first["summary_contract"]["cache_fingerprint"]
    staff_user(app, "empty-team-admin", "ADMIN", stable_id("empty-team"))
    with app.state.session_factory.begin() as session:
        session.execute(
            user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=stable_id("empty-team"))
        )
    assert overview(client, admin).json()["summary_contract"]["cache_fingerprint"] != second


@pytest.mark.postgres
def test_customer360_repeatable_read_prevents_mixed_permission_snapshots(client, headers, app, monkeypatch):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL repeatable-read verification")
    tid = make_ticket(client, headers, app)
    team_b = stable_id("team-b")
    staff_user(app, "agent-b", team_id=team_b)
    agent = login_as(client, "agent")
    original = customer360.visible_tickets
    called = False

    def concurrent_reassignment(session, user, customer_id, purpose):
        nonlocal called
        assert (
            session.scalar(__import__("sqlalchemy").text("SHOW transaction_isolation")) == "repeatable read"
        )
        result = original(session, user, customer_id, purpose)
        if not called:
            called = True
            with app.state.session_factory.begin() as writer:
                writer.execute(
                    tickets.update().where(tickets.c.ticket_id == tid).values(team_id=team_b, version=2)
                )
        return result

    monkeypatch.setattr(customer360, "visible_tickets", concurrent_reassignment)
    current = overview(client, agent)
    assert current.status_code == 200, current.text
    assert current.json()["total_ticket_count"] == 1
    assert current.json()["recent_tickets"][0]["current_assignment"]["team_id"] == stable_id("team")
    assert overview(client, agent).status_code == 404
