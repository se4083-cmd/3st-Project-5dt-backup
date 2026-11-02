"""Minimal audit data. Never copy payloads, raw messages, credentials, or error text."""

import logging
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.models import audit_events

logger = logging.getLogger("csflow.audit")


def record(
    session,
    actor,
    action,
    target_type,
    target_id,
    *,
    result="SUCCESS",
    reason="AUTHORIZED",
    ticket=None,
    cycle=None,
    service="backend-a",
):
    session.execute(
        audit_events.insert().values(
            event_id=str(uuid4()),
            actor_user_id=actor,
            actor_service=service,
            action=action,
            target_type=target_type,
            target_id=target_id,
            event_key=str(uuid4()),
            ticket_id=ticket,
            cycle_no=cycle,
            result=result,
            reason_code=reason,
            payload={},
        )
    )


def record_denial(factory, error):
    # Called only after the request session has rolled back and closed.
    # An independent committed transaction survives request failure.
    try:
        with factory.begin() as session:
            record(
                session,
                error.actor_id,
                "ACCESS_DENIED",
                error.target_type or "API",
                error.target_id,
                result="DENIED",
                reason=error.code,
            )
    except SQLAlchemyError:
        # DB outage prevents DB audit. Emit only a fixed operational signal.
        logger.error("audit_persistence_unavailable")
