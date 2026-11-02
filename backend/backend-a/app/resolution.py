"""Shared resolution gate. Caller holds the ticket lock until final writes commit.

All followup writers lock the parent ticket first, so blocker checks cannot race
with compliant followup creation/changes. This is not a B human-response engine.
"""

from sqlalchemy import exists, select

from app import repository
from app.models import followup_actions, tickets


class WorkRejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def assert_no_blocking_followups(session, ticket_id):
    # Every open mandatory action blocks, regardless of origin/responsibility cycle or owner.
    if session.scalar(
        select(
            exists().where(
                followup_actions.c.ticket_id == ticket_id,
                followup_actions.c.blocks_resolution.is_(True),
                followup_actions.c.status.in_(["OPEN", "IN_PROGRESS"]),
            )
        )
    ):
        raise WorkRejected("BLOCKING_FOLLOWUP")


def lock_resolution_gate(session, ticket_id, *, expected_revision, cycle_no, mode, human_user=None):
    ticket = (
        session.execute(select(tickets).where(tickets.c.ticket_id == ticket_id).with_for_update())
        .mappings()
        .first()
    )
    if not ticket:
        raise WorkRejected("TICKET_NOT_FOUND")
    if ticket["version"] != expected_revision or ticket["cycle_no"] != cycle_no:
        raise WorkRejected("STALE_TICKET_REVISION")
    if mode == "HUMAN":
        human_user = repository.get_user(session, human_user["user_id"]) if human_user else None
        if (
            not human_user
            or not human_user["active"]
            or human_user["role"] != "AGENT"
            or ticket["requested_mode"] != "HUMAN"
            or not session.scalar(
                select(exists().where(tickets.c.ticket_id == ticket_id, repository.ticket_scope(human_user)))
            )
        ):
            raise WorkRejected("HUMAN_RESOLUTION_NOT_ALLOWED")
    elif (
        mode != "AUTO" or ticket["requested_mode"] != "AUTO" or ticket["status"] not in {"OPEN", "PROCESSING"}
    ):
        raise WorkRejected("AUTOMATION_NOT_ALLOWED")
    assert_no_blocking_followups(session, ticket_id)
    return ticket
