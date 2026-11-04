import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from backend.app.automation.job_store import get_connection, init_db

router = APIRouter(
    prefix="/api/automation",
    tags=["Backend B - Job Management"],
)

LEASE_SECONDS = 300
MAX_ATTEMPTS = 3


@router.post("/jobs/{job_id}/claim")
def claim_job(job_id: str):
    """실행 가능한 PENDING 작업을 점유한다."""

    init_db()

    now = datetime.now(timezone.utc)
    now_text = now.isoformat()

    lease_token = str(uuid4())
    lease_until = (now + timedelta(seconds=LEASE_SECONDS)).isoformat()

    try:
        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute(
                """
                UPDATE automation_jobs
                SET status = 'RUNNING',
                    attempt = attempt + 1,
                    lease_token = ?,
                    lease_until = ?,
                    updated_at = ?
                WHERE job_id = ?
                  AND status = 'PENDING'
                  AND next_attempt_at <= ?
                  AND attempt < ?
                """,
                (
                    lease_token,
                    lease_until,
                    now_text,
                    job_id,
                    now_text,
                    MAX_ATTEMPTS,
                ),
            )

            if cursor.rowcount == 0:
                existing = connection.execute(
                    """
                    SELECT job_id
                    FROM automation_jobs
                    WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchone()

                if existing is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Automation job not found",
                    )

                raise HTTPException(
                    status_code=409,
                    detail="Job is not available for claiming",
                )

            row = connection.execute(
                """
                SELECT *
                FROM automation_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to claim automation job",
        ) from exc

    return {
        "claimed": True,
        "job": dict(row),
    }
