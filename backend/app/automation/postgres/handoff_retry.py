"""Retry and terminal failure handling for PostgreSQL HANDOFF jobs."""

import random
from datetime import timedelta

from sqlalchemy import select

from app.db import utcnow
from app.jobs import fenced_job_predicate
from app.models import automation_jobs, tickets

MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 30


def retry_handoff_job(
    session_factory,
    job: dict,
    worker_id: str,
    error_code: str,
):
    """Record retry or terminal failure for a leased HANDOFF job."""

    if (
        not isinstance(error_code, str)
        or not error_code
        or len(error_code) > 64
    ):
        raise ValueError("INVALID_ERROR_CODE")

    if not worker_id or not worker_id.strip():
        raise ValueError("INVALID_WORKER_ID")

    with session_factory.begin() as session:
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
            raise RuntimeError("HANDOFF_LEASE_INVALID")

        if (
            current_job["ticket_id"] != ticket["ticket_id"]
            or current_job["job_kind"] != "HANDOFF"
            or current_job["lease_owner"] != worker_id
            or ticket["cycle_no"] != current_job["cycle_no"]
            or ticket["version"] != current_job["expected_ticket_version"]
            or ticket["requested_mode"] != "HUMAN"
            or ticket["status"] != "HANDOFF_PENDING"
        ):
            raise RuntimeError("HANDOFF_CONTEXT_CHANGED")


        attempt = current_job["attempt"]
        now = utcnow()

        if attempt >= MAX_ATTEMPTS:
            new_status = "FAILED"
            delay = None
            next_attempt_at = now
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
            raise RuntimeError("HANDOFF_LEASE_CHANGED")

        return {
            "job_id": job["job_id"],
            "status": new_status,
            "attempt": attempt,
            "delay_seconds": round(delay, 2) if delay is not None else None,
        }
