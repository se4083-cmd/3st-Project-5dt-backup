"""Customer cycle commands. Lock order: user -> ticket -> jobs -> assignments.

The caller owns the outer transaction. No external I/O or B processing runs here.
"""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import case, select

from app import audit
from app import repository as repo
from app.db import utcnow
from app.errors import APIError, denied
from app.model_constraints import idempotency_keys
from app.models import assignments, automation_jobs, messages, tickets, users
from app.schemas import TicketActionReceipt

REOPENABLE = frozenset(
    {
        "OPEN",
        "PROCESSING",
        "WAITING_CUSTOMER",
        "HANDOFF_PENDING",
        "ASSIGNED",
        "IN_PROGRESS",
        "FOLLOWUP_PENDING",
        "RESOLVED",
    }
)
HUMAN_ACTIVE = frozenset({"HANDOFF_PENDING", "ASSIGNED", "IN_PROGRESS", "FOLLOWUP_PENDING"})


def is_human_path(ticket):
    return (
        ticket["requested_mode"] == "HUMAN"
        or ticket["resolution_mode"] == "HUMAN"
        or ticket["status"] in HUMAN_ACTIVE
    )


def change_cycle(session, user, ticket_id, body, key, *, operation):
    if operation not in {"REOPEN", "REQUEST_AGENT"}:
        raise ValueError("Unsupported customer operation")
    customer = repo.customer_for(session, user)
    # This also serializes cross-ticket/cross-endpoint reuse of one user's key.
    session.execute(select(users.c.user_id).where(users.c.user_id == user["user_id"]).with_for_update()).one()
    ticket = (
        session.execute(
            select(tickets)
            .where(tickets.c.ticket_id == ticket_id, tickets.c.customer_id == customer["customer_id"])
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not ticket:
        raise denied(user["user_id"], "TICKET", ticket_id)
    canonical = json.dumps(
        {"operation": operation, "ticket_id": ticket_id, "body": body.model_dump(mode="json")},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    existing = repo.row(
        session,
        idempotency_keys,
        idempotency_keys.c.user_id == user["user_id"],
        idempotency_keys.c.key == key,
    )
    if existing:
        if existing["operation"] != operation or existing["request_hash"] != digest:
            raise APIError(409, "IDEMPOTENCY_CONFLICT")
        return existing["response_snapshot"], True
    if ticket["version"] != body.expected_revision:
        raise APIError(409, "TICKET_REVISION_CONFLICT")
    if ticket["status"] not in REOPENABLE:
        raise APIError(409, "TICKET_TRANSITION_NOT_ALLOWED")
    if operation == "REQUEST_AGENT" and (
        ticket["status"] in HUMAN_ACTIVE
        or (ticket["requested_mode"] == "HUMAN" and ticket["status"] == "WAITING_CUSTOMER")
    ):
        # A different key cannot enqueue a second assignment request.
        raise APIError(409, "HUMAN_REQUEST_ALREADY_ACTIVE")

    now = utcnow()
    human = operation == "REQUEST_AGENT" or is_human_path(ticket)
    cycle = ticket["cycle_no"] + 1
    revision = ticket["version"] + 1
    message_id = str(uuid4())
    result = TicketActionReceipt(
        ticket_id=ticket_id,
        cycle_no=cycle,
        revision=revision,
        stage="WAITING_FOR_SUPPORT" if human else "RECEIVED",
        handling_mode="HUMAN" if human else "AUTOMATED",
        requested_at=now,
    ).model_dump(mode="json")
    reason = body.reason_code if operation == "REQUEST_AGENT" else ("HUMAN_CONTINUATION" if human else None)
    with session.begin_nested():
        # Lock jobs in deterministic order, shared with worker commit/claim code.
        session.execute(
            select(automation_jobs.c.job_id)
            .where(automation_jobs.c.ticket_id == ticket_id)
            .order_by(automation_jobs.c.job_id)
            .with_for_update()
        ).all()
        session.execute(
            automation_jobs.update()
            .where(
                automation_jobs.c.ticket_id == ticket_id,
                automation_jobs.c.status.in_(["PENDING", "RUNNING", "RETRY"]),
            )
            .values(
                status="CANCELLED",
                lease_token=None,
                lease_until=None,
                lease_owner=None,
                error_code="SUPERSEDED_BY_CUSTOMER",
                updated_at=now,
            )
        )
        session.execute(
            assignments.update()
            .where(
                assignments.c.ticket_id == ticket_id,
                assignments.c.ended_at.is_(None),
            )
            .values(
                ended_at=case((assignments.c.assigned_at > now, assignments.c.assigned_at), else_=now),
                updated_at=now,
            )
        )
        session.execute(
            tickets.update()
            .where(tickets.c.ticket_id == ticket_id)
            .values(
                cycle_no=cycle,
                version=revision,
                requested_mode="HUMAN" if human else "AUTO",
                status="HANDOFF_PENDING" if human else "OPEN",
                team_id=None,
                resolution_mode=None,
                resolved_at=None,
                first_replied_at=None,
                last_error_code=None,
                sla_due_at=now + timedelta(hours=24),
                updated_at=now,
            )
        )
        session.execute(
            messages.insert().values(
                message_id=message_id,
                ticket_id=ticket_id,
                cycle_no=cycle,
                role="CUSTOMER",
                direction="IN",
                visibility="PUBLIC",
                body=body.message,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            automation_jobs.insert().values(
                job_id=str(uuid4()),
                ticket_id=ticket_id,
                cycle_no=cycle,
                expected_ticket_version=revision,
                job_kind="HANDOFF" if human else "AUTO",
                source_message_id=message_id,
                reason_code=reason,
                status="PENDING",
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            idempotency_keys.insert().values(
                user_id=user["user_id"],
                key=key,
                operation=operation,
                request_hash=digest,
                ticket_id=ticket_id,
                response_snapshot=result,
                created_at=now,
            )
        )
        audit.record(
            session,
            user["user_id"],
            "TICKET_REOPENED" if operation == "REOPEN" else "AGENT_REQUESTED",
            "TICKET",
            ticket_id,
            reason=reason or "CUSTOMER_REOPENED",
            ticket=ticket_id,
            cycle=cycle,
        )
        from app.automation_monitor import customer_cycle

        customer_cycle(session, ticket, cycle, "HUMAN" if human else "AUTO", revision, now, reason)
    return result, False
