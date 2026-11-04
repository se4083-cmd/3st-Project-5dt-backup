import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from backend.app.automation.job_store import get_connection, init_db

router = APIRouter(
    prefix="/api/automation",
    tags=["Backend B - Job Management"],
)

MAX_ATTEMPTS = 3


@router.post("/jobs/recover-expired")
def recover_expired_jobs():
    """Lease가 만료된 RUNNING 작업을 복구한다."""

    init_db()

    now = datetime.now(timezone.utc)
    now_text = now.isoformat()

    recovered = []
    handed_off = []

    try:
        with get_connection() as connection:
            # 동시 복구 요청을 직렬화한다.
            connection.execute("BEGIN IMMEDIATE")

            expired_jobs = connection.execute(
                """
                SELECT *
                FROM automation_jobs
                WHERE status = 'RUNNING'
                  AND lease_until IS NOT NULL
                  AND lease_until <= ?
                ORDER BY lease_until
                """,
                (now_text,),
            ).fetchall()

            for job in expired_jobs:
                job_id = job["job_id"]
                attempt = job["attempt"]

                if attempt < MAX_ATTEMPTS:
                    new_status = "PENDING"
                    action = "AUTOMATION_JOB_LEASE_RECOVERED"
                else:
                    new_status = "HANDED_OFF"
                    action = "AUTOMATION_JOB_HANDOFF_REQUIRED"

                # 기존 Lease 토큰을 폐기한다.
                connection.execute(
                    """
                    UPDATE automation_jobs
                    SET status = ?,
                        next_attempt_at = ?,
                        lease_token = NULL,
                        lease_until = NULL,
                        error_code = 'LEASE_EXPIRED',
                        updated_at = ?
                    WHERE job_id = ?
                      AND status = 'RUNNING'
                    """,
                    (
                        new_status,
                        now_text,
                        now_text,
                        job_id,
                    ),
                )

                event_id = str(uuid4())

                # 같은 실행 시도의 Lease 만료 이벤트 중복 방지
                event_key = (
                    f"automation_job:{job_id}:" f"attempt:{attempt}:lease_expired"
                )

                payload = json.dumps(
                    {
                        "job_id": job_id,
                        "previous_status": "RUNNING",
                        "status": new_status,
                        "attempt": attempt,
                        "error_code": "LEASE_EXPIRED",
                        "handoff_required": new_status == "HANDED_OFF",
                    },
                    ensure_ascii=False,
                )

                connection.execute(
                    """
                    INSERT INTO audit_events (
                        event_id,
                        ticket_id,
                        cycle_no,
                        actor_user_id,
                        actor_service,
                        action,
                        target_type,
                        target_id,
                        event_key,
                        payload,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        job["ticket_id"],
                        job["cycle_no"],
                        None,
                        "backend-b",
                        action,
                        "automation_job",
                        job_id,
                        event_key,
                        payload,
                        now_text,
                    ),
                )

                result = {
                    "job_id": job_id,
                    "ticket_id": job["ticket_id"],
                    "attempt": attempt,
                    "status": new_status,
                    "audit_event_id": event_id,
                }

                if new_status == "PENDING":
                    recovered.append(result)
                else:
                    handed_off.append(result)

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to recover expired automation jobs",
        ) from exc

    return {
        "recovered_count": len(recovered),
        "handed_off_count": len(handed_off),
        "recovered": recovered,
        "handed_off": handed_off,
    }
