from uuid import uuid4

from sqlalchemy import and_, exists, insert, select, update

from app import audit
from app.db import utcnow
from app.model_constraints import team_categories, user_team_scopes
from app.models import (
    assignments,
    teams,
    tickets,
    users,
)


class AssignmentRejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def assign_handoff_ticket(
    session,
    *,
    ticket_id: str,
    agent_id: str,
    expected_revision: int,
    reason_code: str = "AUTO_FAILED_HANDOFF",
):
    """
    Assign a HANDOFF_PENDING ticket to an active AGENT.

    The caller owns the transaction and must commit or roll back.
    """

    # 1. Lock ticket to serialize assignment attempts.
    ticket = (
        session.execute(
            select(tickets).where(tickets.c.ticket_id == ticket_id).with_for_update()
        )
        .mappings()
        .first()
    )

    if ticket is None:
        raise AssignmentRejected("TICKET_NOT_FOUND")

    if ticket["version"] != expected_revision:
        raise AssignmentRejected("STALE_TICKET_REVISION")

    if ticket["status"] != "HANDOFF_PENDING":
        raise AssignmentRejected("TICKET_NOT_HANDOFF_PENDING")

    if ticket["requested_mode"] != "HUMAN":
        raise AssignmentRejected("HUMAN_HANDOFF_REQUIRED")

    # 2. Validate target agent.
    agent = (
        session.execute(select(users).where(users.c.user_id == agent_id))
        .mappings()
        .first()
    )

    if (
        agent is None
        or not agent["active"]
        or agent["role"] != "AGENT"
        or agent["team_id"] is None
    ):
        raise AssignmentRejected("AGENT_NOT_ELIGIBLE")

    team_id = agent["team_id"]

    # 3. A ticket with an existing team cannot be silently rerouted.
    if ticket["team_id"] is not None and ticket["team_id"] != team_id:
        raise AssignmentRejected("TICKET_TEAM_MISMATCH")

    # 4. Team must be active.
    team_active = session.scalar(
        select(
            exists().where(
                teams.c.team_id == team_id,
                teams.c.active.is_(True),
            )
        )
    )
    if not team_active:
        raise AssignmentRejected("TEAM_NOT_ACTIVE")

    # 5. Agent must have an explicit team grant.
    has_scope = session.scalar(
        select(
            exists().where(
                user_team_scopes.c.user_id == agent_id,
                user_team_scopes.c.team_id == team_id,
            )
        )
    )
    if not has_scope:
        raise AssignmentRejected("AGENT_TEAM_SCOPE_DENIED")

    # 6. Team must support this ticket category.
    supports_category = session.scalar(
        select(
            exists().where(
                team_categories.c.team_id == team_id,
                team_categories.c.category == ticket["category"],
            )
        )
    )
    if not supports_category:
        raise AssignmentRejected("TEAM_CATEGORY_UNSUPPORTED")

    # 7. Reject an existing active assignment.
    already_assigned = session.scalar(
        select(
            exists().where(
                assignments.c.ticket_id == ticket_id,
                assignments.c.ended_at.is_(None),
            )
        )
    )
    if already_assigned:
        raise AssignmentRejected("ACTIVE_ASSIGNMENT_EXISTS")

    now = utcnow()
    assignment_id = str(uuid4())

    # 8. Create assignment.
    session.execute(
        insert(assignments).values(
            assignment_id=assignment_id,
            ticket_id=ticket_id,
            cycle_no=ticket["cycle_no"],
            team_id=team_id,
            agent_id=agent_id,
            assigned_at=now,
            ended_at=None,
            reason_code=reason_code,
            created_at=now,
            updated_at=now,
        )
    )

    # 9. Update ticket without changing cycle or SLA.
    result = session.execute(
        update(tickets)
        .where(
            and_(
                tickets.c.ticket_id == ticket_id,
                tickets.c.version == expected_revision,
                tickets.c.cycle_no == ticket["cycle_no"],
                tickets.c.status == "HANDOFF_PENDING",
            )
        )
        .values(
            status="ASSIGNED",
            team_id=team_id,
            version=expected_revision + 1,
            updated_at=now,
        )
    )

    if result.rowcount != 1:
        raise AssignmentRejected("TICKET_ASSIGNMENT_CONFLICT")

    # 10. Record audit event in the same transaction.
    audit.record(
        session,
        actor=None,
        action="HANDOFF_TICKET_ASSIGNED",
        target_type="TICKET",
        target_id=ticket_id,
        reason=reason_code,
        ticket=ticket_id,
        cycle=ticket["cycle_no"],
        service="backend-b",
    )

    return {
        "assignment_id": assignment_id,
        "ticket_id": ticket_id,
        "agent_id": agent_id,
        "team_id": team_id,
        "cycle_no": ticket["cycle_no"],
        "ticket_version": expected_revision + 1,
        "status": "ASSIGNED",
    }
