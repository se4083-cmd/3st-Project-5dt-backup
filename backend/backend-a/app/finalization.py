"""Shared storage boundary for B's approved automatic reply; this is not the B engine.

No public HTTP endpoint. B must perform policy/AI checks before calling this function.
All writers must use the same ticket -> job lock order and this fencing boundary.
"""

from uuid import UUID, uuid4

from pydantic import Field
from sqlalchemy import exists, select

from app import audit, quality_provenance
from app.automation_control import assert_automatic_allowed
from app.db import utcnow
from app.models import automation_jobs, messages, tickets
from app.quality_schemas import ReplyProvenance
from app.resolution import WorkRejected, assert_no_blocking_followups
from app.schemas import ReopenRequest


class AutomaticReply(ReopenRequest):
    job_id: UUID
    lease_token: UUID
    worker_id: str = Field(min_length=1, max_length=128)
    cycle_no: int = Field(ge=1)
    automation_generation: int | None = Field(default=None, ge=1)
    provenance: ReplyProvenance | None = None


def commit_automatic_reply(session, command: AutomaticReply):
    """Caller uses factory.begin(); no commit/network call is performed here.

    Lease expiry is checked again after every blocking gate, immediately before
    writes, using wall-clock time (never transaction_timestamp()). A savepoint
    makes the writes atomic even if a caller catches a persistence exception.
    """
    ticket_id = session.scalar(
        select(automation_jobs.c.ticket_id).where(automation_jobs.c.job_id == str(command.job_id))
    )
    if ticket_id is None:
        raise WorkRejected("WORK_NOT_FOUND")
    ticket = (
        session.execute(select(tickets).where(tickets.c.ticket_id == ticket_id).with_for_update())
        .mappings()
        .one()
    )
    job = (
        session.execute(
            select(automation_jobs).where(automation_jobs.c.job_id == str(command.job_id)).with_for_update()
        )
        .mappings()
        .one()
    )
    now = utcnow()
    if (
        ticket["cycle_no"] != command.cycle_no
        or ticket["version"] != command.expected_revision
        or job["cycle_no"] != command.cycle_no
        or job["expected_ticket_version"] != command.expected_revision
    ):
        raise WorkRejected("STALE_TICKET_REVISION")
    if (
        ticket["requested_mode"] != "AUTO"
        or ticket["resolution_mode"] == "HUMAN"
        or ticket["status"] not in {"OPEN", "PROCESSING"}
        or job["job_kind"] != "AUTO"
    ):
        raise WorkRejected("AUTOMATION_NOT_ALLOWED")
    if (
        job["status"] != "RUNNING"
        or job["lease_token"] != str(command.lease_token)
        or job["lease_owner"] != command.worker_id
        or job["lease_until"] is None
        or job["lease_until"] <= now
    ):
        raise WorkRejected("INVALID_LEASE")
    if session.scalar(
        select(
            exists().where(
                messages.c.ticket_id == ticket_id,
                messages.c.cycle_no == command.cycle_no,
                messages.c.final_reply.is_(True),
                messages.c.direction == "OUT",
            )
        )
    ):
        raise WorkRejected("FINAL_REPLY_ALREADY_EXISTS")
    assert_no_blocking_followups(session, ticket_id)
    # Keep the SHARE fence until the same transaction finishes all final writes.
    assert_automatic_allowed(session, job["automation_generation"])
    if (
        command.automation_generation is not None
        and command.automation_generation != job["automation_generation"]
    ):
        raise WorkRejected("AUTOMATION_GENERATION_CHANGED")
    message_id = str(uuid4())
    prepared = quality_provenance.prepare(session, command, ticket, job, utcnow())
    with session.begin_nested():
        # Control SHARE acquisition and other gates may have waited beyond the
        # lease checked above. Ticket/job locks retain all other fence values.
        now = utcnow()
        if job["lease_until"] <= now:
            raise WorkRejected("INVALID_LEASE")
        if prepared[2] is not None and prepared[2] <= now:
            raise WorkRejected("PROVENANCE_EXPIRED")
        session.execute(
            messages.insert().values(
                message_id=message_id,
                ticket_id=ticket_id,
                cycle_no=command.cycle_no,
                role="SYSTEM",
                direction="OUT",
                visibility="PUBLIC",
                body=command.message,
                final_reply=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            tickets.update()
            .where(tickets.c.ticket_id == ticket_id)
            .values(
                status="RESOLVED",
                resolution_mode="AUTO",
                version=ticket["version"] + 1,
                resolved_at=now,
                first_replied_at=ticket["first_replied_at"] or now,
                updated_at=now,
            )
        )
        quality_provenance.persist(session, message_id, ticket, job, command, prepared, now)
        session.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == str(command.job_id))
            .values(
                status="SUCCEEDED",
                lease_owner=None,
                lease_token=None,
                lease_until=None,
                updated_at=now,
            )
        )
        audit.record(
            session,
            None,
            "AUTOMATIC_REPLY_COMMITTED",
            "TICKET",
            ticket_id,
            reason="FENCED_COMMIT",
            ticket=ticket_id,
            cycle=command.cycle_no,
        )
    return {
        "message_id": message_id,
        "ticket_id": ticket_id,
        "cycle_no": command.cycle_no,
        "revision": ticket["version"] + 1,
    }
