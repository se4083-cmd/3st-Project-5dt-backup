"""PostgreSQL retry and terminal failure handling for AUTO jobs."""

import random
from datetime import timedelta

from sqlalchemy import select

from app.automation_control import assert_automatic_allowed
from app.db import utcnow
from app.jobs import fenced_job_predicate
from app.models import automation_jobs, tickets
from app import audit

MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 30


def retry_auto_job(
    session_factory,
    job: dict,
    worker_id: str,
    error_code: str,
):
    """Record a retry or terminal failure for a leased AUTO job."""

    if not isinstance(error_code, str) or not error_code or len(error_code) > 64:
        raise ValueError("Invalid error_code")

    with session_factory.begin() as session:
        # Lock ticket before job, matching Backend A's lock order.
        ticket = (
            session.execute(
                select(tickets)
                .where(tickets.c.ticket_id == job["ticket_id"])
                .with_for_update()
            )
            .mappings()
            .one()
        )

        current_job = (
            session.execute(
                select(automation_jobs)
                .where(
                    fenced_job_predicate(
                        job["job_id"],
                        job["lease_token"],
                        job["expected_ticket_version"],
                        job["cycle_no"],
                    )
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

        if current_job is None:
            raise RuntimeError("JOB_LEASE_INVALID")

        if (
            current_job["ticket_id"] != ticket["ticket_id"]
            or current_job["job_kind"] != "AUTO"
            or current_job["lease_owner"] != worker_id
            or ticket["cycle_no"] != current_job["cycle_no"]
            or ticket["version"] != current_job["expected_ticket_version"]
            or ticket["requested_mode"] != "AUTO"
            or ticket["status"] not in ("OPEN", "PROCESSING")
        ):
            raise RuntimeError("JOB_CONTEXT_CHANGED")

        assert_automatic_allowed(
            session,
            current_job["automation_generation"],
        )

        attempt = current_job["attempt"]
        now = utcnow()

        if attempt >= MAX_ATTEMPTS:
            new_status = "FAILED"
            next_attempt_at = now
            delay = None
        else:
            new_status = "RETRY"
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            delay += random.uniform(0, 5)
            next_attempt_at = now + timedelta(seconds=delay)

        result = session.execute(
            automation_jobs.update()
            .where(
                fenced_job_predicate(
                    job["job_id"],
                    job["lease_token"],
                    job["expected_ticket_version"],
                    job["cycle_no"],
                )
            )
            .values(
                status=new_status,
                next_attempt_at=next_attempt_at,
                error_code=error_code,
                lease_token=None,
                lease_owner=None,
                lease_until=None,
                updated_at=now,
            )
        )

        if result.rowcount != 1:
            raise RuntimeError("JOB_LEASE_CHANGED")

        # Terminal AUTO failure: transition the ticket to human handling.
        # Both updates are committed or rolled back together.
        if new_status == "FAILED":
            ticket_result = session.execute(
                tickets.update()
                .where(
                    tickets.c.ticket_id == ticket["ticket_id"],
                    tickets.c.cycle_no == current_job["cycle_no"],
                    tickets.c.version == current_job["expected_ticket_version"],
                    tickets.c.requested_mode == "AUTO",
                    tickets.c.status.in_(["OPEN", "PROCESSING"]),
                )
                .values(
                    requested_mode="HUMAN",
                    status="HANDOFF_PENDING",
                    version=ticket["version"] + 1,
                    last_error_code=error_code,
                    updated_at=now,
                )
            )

            if ticket_result.rowcount != 1:
                raise RuntimeError("TICKET_HANDOFF_CONFLICT")

            audit.record(
                session,
                actor=None,
                action="AUTO_JOB_FAILED_HANDOFF",
                target_type="TICKET",
                target_id=ticket["ticket_id"],
                reason=error_code,
                ticket=ticket["ticket_id"],
                cycle=current_job["cycle_no"],
                service="backend-b",
            )

        return {
            "status": new_status,
            "job_id": job["job_id"],
            "attempt": attempt,
            "delay_seconds": round(delay, 2) if delay is not None else None,
        }
