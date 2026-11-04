import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from backend.app.automation.job_store import (
    get_connection,
    init_db,
)
from backend.app.automation.mock_context import (
    load_json,
    find_one,
)

router = APIRouter(
    prefix="/api/automation",
    tags=["Backend B - Job Management"],
)


class CreateJobRequest(BaseModel):
    ticket_id: str
    cycle_no: int = Field(ge=1)


@router.post("/jobs")
def create_job(request: CreateJobRequest, response: Response):
    """티켓의 현재 처리 회차에 대한 자동화 작업을 생성한다."""

    # 1. Mock 티켓 존재 여부 확인
    tickets = load_json("tickets.json")
    ticket = find_one(tickets, "ticket_id", request.ticket_id)

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    # 2. 티켓의 현재 회차 검증
    if ticket.get("cycle_no") != request.cycle_no:
        raise HTTPException(
            status_code=409,
            detail="Ticket cycle does not match",
        )

    # 3. 신규 작업 데이터 준비
    now = datetime.now(timezone.utc).isoformat()

    job_id = str(uuid4())

    # 4. SQLite에 저장
    # UNIQUE(ticket_id, cycle_no)가 중복 생성을 방지한다.
    init_db()

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO automation_jobs (
                    job_id,
                    ticket_id,
                    cycle_no,
                    status,
                    attempt,
                    next_attempt_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticket_id, cycle_no)
                DO NOTHING
                """,
                (
                    job_id,
                    request.ticket_id,
                    request.cycle_no,
                    "PENDING",
                    0,
                    now,
                    now,
                    now,
                ),
            )

            created = cursor.rowcount == 1

            # 신규 생성 또는 기존 작업 조회
            row = connection.execute(
                """
                SELECT *
                FROM automation_jobs
                WHERE ticket_id = ?
                  AND cycle_no = ?
                """,
                (request.ticket_id, request.cycle_no),
            ).fetchone()

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to save automation job",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=500,
            detail="Automation job could not be retrieved",
        )

    response.status_code = 201 if created else 200

    return {
        "created": created,
        "job": dict(row),
    }
