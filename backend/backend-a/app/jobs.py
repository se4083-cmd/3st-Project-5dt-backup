"""Backend B database handoff: reservation only, no AI/execution/finalization engine."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select

from app.automation_control import assert_automatic_allowed, read_control
from app.db import utcnow
from app.models import automation_jobs as jobs
from app.models import tickets


def claim_jobs(session, worker_id: str, *, limit=10, lease_seconds=60, job_kind="AUTO"):
    if session.bind.dialect.name != "postgresql":
        raise RuntimeError("Concurrent job leases require PostgreSQL")
    if (
        not worker_id
        or len(worker_id) > 128
        or not 1 <= limit <= 100
        or not 10 <= lease_seconds <= 300
        or job_kind not in {"AUTO", "HANDOFF"}
    ):
        raise ValueError("Invalid lease parameters")
    now = utcnow()
    control = read_control(session) if job_kind == "AUTO" else None
    if control is not None and control["paused"]:
        return []
    eligible = and_(
        jobs.c.next_attempt_at <= now,
        jobs.c.job_kind == job_kind,
        or_(
            jobs.c.status.in_(["PENDING", "RETRY"]),
            and_(
                jobs.c.status == "RUNNING",
                or_(
                    jobs.c.lease_until <= now,
                    jobs.c.automation_generation != control["generation"] if control is not None else False,
                ),
            ),
        ),
        jobs.c.cycle_no == tickets.c.cycle_no,
        jobs.c.expected_ticket_version == tickets.c.version,
        tickets.c.requested_mode == ("AUTO" if job_kind == "AUTO" else "HUMAN"),
        tickets.c.status.in_(["OPEN", "PROCESSING"] if job_kind == "AUTO" else ["HANDOFF_PENDING"]),
    )
    candidates = (
        session.execute(
            select(tickets.c.ticket_id)
            .join(jobs, jobs.c.ticket_id == tickets.c.ticket_id)
            .where(eligible)
            .order_by(jobs.c.next_attempt_at, jobs.c.job_id)
            .limit(limit)
            .with_for_update(of=tickets, skip_locked=True)
        )
        .scalars()
        .all()
    )
    claimed = []
    for ticket_id in candidates:
        # Same ticket -> job order as reopen/handoff and final reply commit.
        job = (
            session.execute(
                select(jobs)
                .join(tickets, jobs.c.ticket_id == tickets.c.ticket_id)
                .where(eligible, jobs.c.ticket_id == ticket_id)
                .with_for_update(of=jobs)
            )
            .mappings()
            .first()
        )
        if not job:
            continue
        if job_kind == "AUTO":
            assert_automatic_allowed(session, control["generation"])
        now = utcnow()
        values = {
            "status": "RUNNING",
            "lease_token": str(uuid4()),
            "lease_owner": worker_id,
            "lease_until": now + timedelta(seconds=lease_seconds),
            "attempt": job["attempt"] + 1,
            "updated_at": now,
        }
        if control is not None:
            values["automation_generation"] = control["generation"]
        session.execute(jobs.update().where(jobs.c.job_id == job["job_id"]).values(**values))
        claimed.append({**job, **values})
    # Caller MUST commit before any network operation. Tokens are not logged.
    return claimed


def fenced_job_predicate(job_id, lease_token, expected_version, cycle_no):
    """Legacy job-side predicate only; NOT the global stop or full ticket fence.

    Use commit_automatic_reply for final storage. B must also integrate the
    shared control gate before work/retries/heartbeat/dispatch.
    """
    return and_(
        jobs.c.job_id == job_id,
        jobs.c.lease_token == lease_token,
        jobs.c.status == "RUNNING",
        jobs.c.lease_until > utcnow(),
        jobs.c.expected_ticket_version == expected_version,
        jobs.c.cycle_no == cycle_no,
    )
