import json
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.automation.job_store import get_connection, init_db

router = APIRouter(
    prefix="/api/automation",
    tags=["Backend B - Job Management"],
)

MAX_ATTEMPTS = 3


class FailJobRequest(BaseModel):
    lease_token: str = Field(min_length=1)
    error_code: str = Field(min_length=1, max_length=100)
    retryable: bool


@router.post("/jobs/{job_id}/fail")
def fail_job(job_id: str, request: FailJobRequest):
    """실패 처리, 재시도 예약 또는 이관 대상 전환 및 감사 기록."""

    init_db()

    now = datetime.now(timezone.utc)
    now_text = now.isoformat()

    try:
        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")

            # 1. 현재 작업 조회
            job = connection.execute(
                """
                SELECT *
                FROM automation_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()

            if job is None:
                raise HTTPException(
                    status_code=404,
                    detail="Automation job not found",
                )

            # 2. 실행 권한 검증
            if (
                job["status"] != "RUNNING"
                or job["lease_token"] != request.lease_token
                or job["lease_until"] is None
                or job["lease_until"] <= now_text
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Job is not running, token is invalid, or lease expired",
                )

            attempt = job["attempt"]

            # 3. 재시도 또는 이관 대상 결정
            if request.retryable and attempt < MAX_ATTEMPTS:
                delay_seconds = 30 * (2 ** (attempt - 1))
                next_attempt_at = (now + timedelta(seconds=delay_seconds)).isoformat()

                new_status = "PENDING"
                action = "AUTOMATION_JOB_RETRY_SCHEDULED"
            else:
                next_attempt_at = now_text
                new_status = "HANDED_OFF"
                action = "AUTOMATION_JOB_HANDOFF_REQUIRED"

            # 4. 작업 상태 변경
            connection.execute(
                """
                UPDATE automation_jobs
                SET status = ?,
                    next_attempt_at = ?,
                    lease_token = NULL,
                    lease_until = NULL,
                    error_code = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (
                    new_status,
                    next_attempt_at,
                    request.error_code,
                    now_text,
                    job_id,
                ),
            )

            updated_job = connection.execute(
                """
                SELECT *
                FROM automation_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()

            # 5. 감사 이벤트 생성
            event_id = str(uuid4())
            event_key = f"automation_job:{job_id}:attempt:{attempt}:failed"

            payload = json.dumps(
                {
                    "job_id": job_id,
                    "status": new_status,
                    "attempt": attempt,
                    "error_code": request.error_code,
                    "retryable": request.retryable,
                    "next_attempt_at": next_attempt_at,
                    "handoff_required": new_status == "HANDED_OFF",
                },
                ensure_ascii=False,
            )

            # 6. 감사 이벤트 DB 저장
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
                    updated_job["ticket_id"],
                    updated_job["cycle_no"],
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

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to update automation job or save audit event",
        ) from exc

    return {
        "failed": True,
        "retry_scheduled": new_status == "PENDING",
        "handed_off": new_status == "HANDED_OFF",
        "job": dict(updated_job),
        "audit_event": {
            "event_id": event_id,
            "event_key": event_key,
            "action": action,
        },
    }
