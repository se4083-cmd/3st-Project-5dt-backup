from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import audit
from app.db import utcnow
from app.model_constraints import idempotency_keys
from app.models import audit_events, followup_actions, tickets, users
from app.seed import stable_id
from tests.conftest import login_as
from tests.phase3_helpers import change_state, create_followup, followup_detail, make_ticket, staff_user


def test_ticket_followup_crud_and_public_whitelist(client, headers, app):
    ticket_id = make_ticket(client, headers, app)
    agent = login_as(client, "agent")
    created = create_followup(client, agent, ticket_id)
    assert created.status_code == 201, created.text
    action_id = created.json()["action_id"]
    staff = followup_detail(client, agent, action_id).json()
    assert staff["internal_note"] == "PRIVATE_INTERNAL_NOTE" and staff["revision"] == 1
    public = client.get(f"/api/v1/followups/{action_id}", headers=headers)
    assert public.status_code == 200
    assert set(public.json()) == {
        "action_id",
        "ticket_id",
        "cycle_no",
        "status",
        "public_note",
        "due_at",
        "completed_at",
        "updated_at",
    }
    assert "PRIVATE" not in public.text
    edited = client.patch(
        f"/api/v1/staff/followups/{action_id}",
        headers=agent,
        json={
            "expected_revision": 1,
            "public_note": "已确认",
            "due_at": (utcnow() + timedelta(days=1)).isoformat(),
        },
    )
    assert edited.status_code == 200 and edited.json()["revision"] == 2
    assert change_state(client, agent, action_id, "IN_PROGRESS", 2).status_code == 200
    done = change_state(client, agent, action_id, "DONE", 3)
    assert done.status_code == 200 and done.json()["completed_at"] is not None
    assert done.json()["cancelled_at"] is None
    with app.state.session_factory() as session:
        assert (
            session.scalar(select(tickets.c.status).where(tickets.c.ticket_id == ticket_id)) == "IN_PROGRESS"
        )
    assert (
        client.get("/api/v1/followups?limit=1", headers=headers).json()["items"][0]["action_id"] == action_id
    )


def test_private_only_and_product_actions_are_not_customer_visible(client, headers, app):
    ticket_id = make_ticket(client, headers, app)
    agent, admin = login_as(client, "agent"), login_as(client, "admin")
    hidden = create_followup(client, agent, ticket_id, public_note=None).json()["action_id"]
    product = create_followup(
        client,
        admin,
        product_id=stable_id("product"),
        owner_user_id=stable_id("admin"),
        blocks_resolution=False,
        key="product-followup-01",
    )
    assert product.status_code == 201, product.text
    assert client.get("/api/v1/followups", headers=headers).json()["items"] == []
    for aid in [hidden, product.json()["action_id"]]:
        assert client.get(f"/api/v1/followups/{aid}", headers=headers).status_code == 404
    assert followup_detail(client, agent, product.json()["action_id"]).status_code == 404
    assert (
        create_followup(client, agent, product_id=stable_id("product"), blocks_resolution=False).status_code
        == 403
    )
    assert client.get("/api/v1/staff/followups", headers=headers).status_code == 403


def test_followup_cross_customer_and_cross_team_denials(client, headers, app):
    ticket_id = make_ticket(client, headers, app)
    agent = login_as(client, "agent")
    action_id = create_followup(client, agent, ticket_id).json()["action_id"]
    other_customer = login_as(client, "customer2")
    assert client.get(f"/api/v1/followups/{action_id}", headers=other_customer).status_code == 404
    team_b = stable_id("team-b")
    staff_user(app, "admin-b", "ADMIN", team_b)
    staff_user(app, "agent-b", team_id=team_b)
    for label in ["admin-b", "agent-b"]:
        other = login_as(client, label)
        assert followup_detail(client, other, action_id).status_code == 404
        assert client.get("/api/v1/staff/followups", headers=other).json()["items"] == []
    assert (
        create_followup(
            client,
            login_as(client, "admin"),
            ticket_id,
            owner_team_id=team_b,
            owner_user_id=None,
            key="wrong-team-create",
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"product_id": stable_id("product")},
        {"ticket_id": None},
        {"cycle_no": 5},
        {"due_at": "2026-11-03T00:00:00"},
        {"due_at": "2020-01-01T00:00:00Z"},
        {"owner_user_id": str(uuid4())},
        {"kind": " "},
    ],
)
def test_followup_validation(client, headers, app, bad):
    ticket_id = make_ticket(client, headers, app)
    # Keep both IDs for the exclusive-target test; helper normally removes ticket on product input.
    body = {
        "ticket_id": ticket_id,
        "owner_team_id": stable_id("team"),
        "owner_user_id": stable_id("agent"),
        "kind": "CHECK",
        **bad,
    }
    result = client.post(
        "/api/v1/staff/followups",
        json=body,
        headers={**login_as(client, "agent"), "Idempotency-Key": "invalid-followup-key"},
    )
    assert result.status_code in (422, 409)


@pytest.mark.parametrize(
    "start,end,valid",
    [
        ("OPEN", "IN_PROGRESS", True),
        ("OPEN", "DONE", True),
        ("OPEN", "CANCELLED", True),
        ("IN_PROGRESS", "DONE", True),
        ("IN_PROGRESS", "CANCELLED", True),
        ("IN_PROGRESS", "OPEN", False),
        ("DONE", "IN_PROGRESS", False),
        ("CANCELLED", "DONE", False),
    ],
)
def test_followup_transition_matrix(client, headers, app, start, end, valid):
    ticket_id = make_ticket(client, headers, app)
    agent = login_as(client, "agent")
    aid = create_followup(client, agent, ticket_id).json()["action_id"]
    rev = 1
    if start != "OPEN":
        first = change_state(client, agent, aid, start, 1, "OTHER" if start == "CANCELLED" else None)
        assert first.status_code == 200
        rev = first.json()["revision"]
    result = change_state(client, agent, aid, end, rev, "OTHER" if end == "CANCELLED" else None)
    assert result.status_code == (200 if valid else 409)


def test_delete_is_audited_cancellation_and_terminal_immutable(client, headers, app):
    ticket_id = make_ticket(client, headers, app)
    agent = login_as(client, "agent")
    aid = create_followup(client, agent, ticket_id).json()["action_id"]
    path = f"/api/v1/staff/followups/{aid}"
    cancelled = client.request(
        "DELETE",
        path,
        headers=agent,
        json={"expected_revision": 1, "cancellation_reason": "NO_LONGER_NEEDED"},
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["completed_at"] is None and cancelled.json()["cancelled_at"] is not None
    assert followup_detail(client, agent, aid).status_code == 200
    assert (
        client.patch(path, headers=agent, json={"expected_revision": 2, "public_note": "changed"}).status_code
        == 409
    )
    with app.state.session_factory() as session:
        event = (
            session.execute(select(audit_events).where(audit_events.c.action == "FOLLOWUP_STATE_CHANGED"))
            .mappings()
            .one()
        )
        assert event["reason_code"] == "NO_LONGER_NEEDED" and event["payload"] == {}


def test_creation_idempotency_namespace_and_concurrency(client, headers, app):
    ticket_id = make_ticket(client, headers, app)
    agent = login_as(client, "agent")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create_followup(client, agent, ticket_id), range(2)))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json() == results[1].json()
    assert create_followup(client, agent, ticket_id, public_note="different").status_code == 409
    with app.state.session_factory() as session:
        assert len(session.execute(select(followup_actions)).all()) == 1


def test_concurrent_modification_uses_action_revision(client, headers, app):
    ticket_id = make_ticket(client, headers, app)
    agent = login_as(client, "agent")
    aid = create_followup(client, agent, ticket_id).json()["action_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda note: client.patch(
                    f"/api/v1/staff/followups/{aid}",
                    headers=agent,
                    json={"expected_revision": 1, "internal_note": note},
                ),
                ["first", "second"],
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert followup_detail(client, agent, aid).json()["revision"] == 2


@pytest.mark.parametrize("operation", ["create", "patch", "state"])
def test_followup_audit_failure_rolls_back(client, headers, app, monkeypatch, operation):
    ticket_id = make_ticket(client, headers, app)
    agent = login_as(client, "agent")
    aid = create_followup(client, agent, ticket_id).json()["action_id"]
    with app.state.session_factory() as session:
        before = [dict(r) for r in session.execute(select(followup_actions)).mappings()]
        keys = len(session.execute(select(idempotency_keys)).all())
    original = audit.record

    def fail(*args, **kwargs):
        if args[2] in {"FOLLOWUP_CREATED", "FOLLOWUP_UPDATED", "FOLLOWUP_STATE_CHANGED"}:
            raise RuntimeError("late followup write failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(audit, "record", fail)
    if operation == "create":
        result = create_followup(client, agent, ticket_id, key="late-failed-create")
    elif operation == "patch":
        result = client.patch(
            f"/api/v1/staff/followups/{aid}",
            headers=agent,
            json={"expected_revision": 1, "internal_note": "must roll back"},
        )
    else:
        result = change_state(client, agent, aid, "DONE")
    assert result.status_code == 500
    with app.state.session_factory() as session:
        assert [dict(r) for r in session.execute(select(followup_actions)).mappings()] == before
        assert len(session.execute(select(idempotency_keys)).all()) == keys


def test_unowned_or_inactive_owner_remains_in_admin_queue(client, headers, app):
    ticket_id = make_ticket(client, headers, app)
    admin = login_as(client, "admin")
    aid = create_followup(client, admin, ticket_id, owner_user_id=None).json()["action_id"]
    assert followup_detail(client, admin, aid).json()["needs_handover"]
    assert change_state(client, admin, aid, "DONE").status_code == 409
    patched = client.patch(
        f"/api/v1/staff/followups/{aid}",
        headers=admin,
        json={"expected_revision": 1, "owner_user_id": stable_id("admin")},
    )
    assert patched.status_code == 200
    assert change_state(client, admin, aid, "DONE", 2).status_code == 200


def test_inactive_owner_is_not_hidden_from_admin(client, headers, app):
    tid = make_ticket(client, headers, app)
    admin = login_as(client, "admin")
    aid = create_followup(client, admin, tid).json()["action_id"]
    with app.state.session_factory.begin() as session:
        session.execute(users.update().where(users.c.user_id == stable_id("agent")).values(active=False))
    queue = client.get("/api/v1/staff/followups", headers=admin).json()["items"]
    assert queue[0]["action_id"] == aid and queue[0]["needs_handover"]
    assert change_state(client, admin, aid, "DONE").status_code == 409


def test_product_followup_edit_complete_and_owner_rules(client, headers, app):
    admin = login_as(client, "admin")
    created = create_followup(
        client,
        admin,
        product_id=stable_id("product"),
        blocks_resolution=False,
        owner_user_id=stable_id("admin"),
    )
    assert created.status_code == 201
    aid = created.json()["action_id"]
    edited = client.patch(
        f"/api/v1/staff/followups/{aid}",
        headers=admin,
        json={"expected_revision": 1, "internal_note": "product action updated", "public_note": None},
    )
    assert edited.status_code == 200 and edited.json()["cycle_no"] is None
    assert edited.json()["responsibility_cycle_no"] is None
    assert change_state(client, admin, aid, "DONE", 2).status_code == 200
    assert (
        create_followup(
            client,
            admin,
            product_id=stable_id("product"),
            blocks_resolution=False,
            owner_user_id=stable_id("agent"),
            key="product-invalid-owner",
        ).status_code
        == 409
    )


@pytest.mark.parametrize("invalid", ["ended", "cycle", "category", "resolved"])
def test_followup_access_uses_current_ticket_assignment_policy(client, headers, app, invalid):
    from app.models import assignments

    tid = make_ticket(client, headers, app)
    agent = login_as(client, "agent")
    aid = create_followup(client, agent, tid).json()["action_id"]
    with app.state.session_factory.begin() as session:
        if invalid == "ended":
            session.execute(
                assignments.update().where(assignments.c.ticket_id == tid).values(ended_at=utcnow())
            )
        else:
            values = {
                "cycle": {"cycle_no": 2},
                "category": {"category": "PAYMENT"},
                "resolved": {"status": "RESOLVED", "resolution_mode": "HUMAN", "resolved_at": utcnow()},
            }[invalid]
            session.execute(tickets.update().where(tickets.c.ticket_id == tid).values(**values))
    assert followup_detail(client, agent, aid).status_code == 404
    assert client.get("/api/v1/staff/followups", headers=agent).json()["items"] == []
