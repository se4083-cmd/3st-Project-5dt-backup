import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.automation.job_store import get_connection, init_db

router = APIRouter(
    prefix="/api/automation",
    tags=["Backend B - Job Management"],
)


class CompleteJobRequest(BaseModel):
    lease_token: str = Field(min_length=1)


@router.post("/jobs/{job_id}/complete")
def complete_job(job_id: str, request: CompleteJobRequest):
    init_db()
    now_text = datetime.now(timezone.utc).isoformat()

    try:
        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute(
                """
                UPDATE automation_jobs
                SET status = 'SUCCEEDED',
                    lease_token = NULL,
                    lease_until = NULL,
                    updated_at = ?
                WHERE job_id = ?
                  AND status = 'RUNNING'
                  AND lease_token = ?
                  AND lease_until > ?
                """,
                (
                    now_text,
                    job_id,
                    request.lease_token,
                    now_text,
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
                    detail="Job is not running, token is invalid, or lease expired",
                )

            row = connection.execute(
                """
                SELECT *
                FROM automation_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()

            # 완료 감사 이벤트 기록
            event_id = str(uuid4())
            event_key = f"automation_job:{job_id}:succeeded"

            payload = json.dumps(
                {
                    "job_id": job_id,
                    "status": "SUCCEEDED",
                    "attempt": row["attempt"],
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
                    row["ticket_id"],
                    row["cycle_no"],
                    None,
                    "backend-b",
                    "AUTOMATION_JOB_SUCCEEDED",
                    "automation_job",
                    job_id,
                    event_key,
                    payload,
                    now_text,
                ),
            )

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to complete automation job",
        ) from exc

    return {
        "completed": True,
        "job": dict(row),
        "audit_event": {
            "event_id": event_id,
            "event_key": event_key,
            "action": "AUTOMATION_JOB_SUCCEEDED",
        },
    }
