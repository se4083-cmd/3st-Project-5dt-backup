from datetime import datetime, timezone

from backend.app.automation.job_store import get_connection, init_db
from backend.app.automation.job_recovery import recover_expired_jobs
from backend.app.automation.automation_gate import evaluate_gate


def run_once():
    """만료 작업 복구, 실행 대상 조회, 자동화 게이트 검증."""

    init_db()

    recovery_result = recover_expired_jobs()

    print(
        "[RECOVERY]",
        "recovered:",
        recovery_result["recovered_count"],
        "handed_off:",
        recovery_result["handed_off_count"],
    )

    now_text = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                job_id,
                ticket_id,
                cycle_no,
                status,
                attempt,
                next_attempt_at
            FROM automation_jobs
            WHERE status = 'PENDING'
              AND next_attempt_at <= ?
              AND attempt < 3
            ORDER BY next_attempt_at, created_at
            LIMIT 10
            """,
            (now_text,),
        ).fetchall()

    print("[WORKER] Ready jobs:", len(rows))

    allowed_count = 0
    blocked_count = 0

    for row in rows:
        job = dict(row)

        result = evaluate_gate(
            ticket_id=job["ticket_id"],
            cycle_no=job["cycle_no"],
        )

        if result["allowed"]:
            allowed_count += 1
            print(
                "[GATE ALLOWED]",
                "job_id:",
                job["job_id"],
                "ticket_id:",
                job["ticket_id"],
            )
        else:
            blocked_count += 1
            print(
                "[GATE BLOCKED]",
                "job_id:",
                job["job_id"],
                "ticket_id:",
                job["ticket_id"],
                "reason:",
                result["reason"],
            )

    print(
        "[SUMMARY]",
        "allowed:",
        allowed_count,
        "blocked:",
        blocked_count,
    )

    return {
        "recovery": recovery_result,
        "ready_count": len(rows),
        "allowed_count": allowed_count,
        "blocked_count": blocked_count,
    }


if __name__ == "__main__":
    run_once()
