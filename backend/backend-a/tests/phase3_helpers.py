from uuid import uuid4

from sqlalchemy import select

from app.db import utcnow
from app.model_constraints import user_team_scopes
from app.models import assignments, teams, tickets, users
from app.seed import stable_id
from tests.test_flow import submit


def staff_user(app, label, role="AGENT", team_id=None):
    team_id = team_id or stable_id("team")
    user_id = stable_id(label)
    with app.state.session_factory.begin() as session:
        if not session.scalar(select(teams.c.team_id).where(teams.c.team_id == team_id)):
            template = dict(session.execute(select(teams)).mappings().first())
            template.update(team_id=team_id, name=label + " team")
            session.execute(teams.insert().values(**template))
            from app.model_constraints import team_categories

            session.execute(team_categories.insert().values(team_id=team_id, category="DELIVERY"))
        template = dict(
            session.execute(select(users).where(users.c.user_id == stable_id("agent"))).mappings().one()
        )
        template.update(
            user_id=user_id,
            login_name=f"dev-{label}@example.test",
            role=role,
            team_id=team_id if role == "AGENT" else None,
            allowed_team_ids=[team_id],
        )
        session.execute(users.insert().values(**template))
        session.execute(user_team_scopes.insert().values(user_id=user_id, team_id=team_id))
    return user_id


def assign(app, ticket_id, *, agent="agent", team_id=None, cycle=None, status="IN_PROGRESS", mode="HUMAN"):
    """Test fixture only, not a B assignment engine."""
    team_id = team_id or stable_id("team")
    with app.state.session_factory.begin() as session:
        original = session.execute(select(tickets).where(tickets.c.ticket_id == ticket_id)).mappings().one()
        cycle = cycle or original["cycle_no"]
        session.execute(
            assignments.update()
            .where(assignments.c.ticket_id == ticket_id, assignments.c.ended_at.is_(None))
            .values(ended_at=utcnow())
        )
        session.execute(
            tickets.update()
            .where(tickets.c.ticket_id == ticket_id)
            .values(
                team_id=team_id,
                category="DELIVERY",
                status=status,
                cycle_no=cycle,
                requested_mode=mode,
                resolved_at=utcnow() if status == "RESOLVED" else None,
                resolution_mode=mode if status == "RESOLVED" else None,
            )
        )
        session.execute(
            assignments.insert().values(
                assignment_id=str(uuid4()),
                ticket_id=ticket_id,
                cycle_no=cycle,
                team_id=team_id,
                agent_id=stable_id(agent),
                assigned_at=utcnow(),
                reason_code="TEST_ONLY",
            )
        )


def make_ticket(client, headers, app, *, key="phase3-ticket-01", assigned=True):
    result = submit(client, headers, key=key)
    assert result.status_code == 201, result.text
    ticket_id = result.json()["ticket_id"]
    if assigned:
        assign(app, ticket_id)
    else:
        with app.state.session_factory.begin() as session:
            session.execute(
                tickets.update()
                .where(tickets.c.ticket_id == ticket_id)
                .values(team_id=stable_id("team"), category="DELIVERY")
            )
    return ticket_id


def create_followup(client, staff_headers, ticket_id=None, *, key="phase3-followup-01", **changes):
    body = {
        "ticket_id": ticket_id,
        "owner_team_id": stable_id("team"),
        "owner_user_id": stable_id("agent"),
        "kind": "INTERNAL_CHECK",
        "public_note": "공개 확인 중",
        "internal_note": "PRIVATE_INTERNAL_NOTE",
        "blocks_resolution": True,
        **changes,
    }
    if body.get("product_id"):
        body.pop("ticket_id", None)
    return client.post(
        "/api/v1/staff/followups", headers={**staff_headers, "Idempotency-Key": key}, json=body
    )


def followup_detail(client, staff_headers, action_id):
    return client.get(f"/api/v1/staff/followups/{action_id}", headers=staff_headers)


def change_state(client, staff_headers, action_id, status, revision=1, reason=None):
    return client.post(
        f"/api/v1/staff/followups/{action_id}/status",
        headers=staff_headers,
        json={"expected_revision": revision, "status": status, "cancellation_reason": reason},
    )
