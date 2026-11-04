"""Regression test for unverified automatic replies."""

from unittest.mock import patch

from backend.app.automation.postgres import worker


def test_unverified_reply_must_not_finalize():
    job = {
        "job_id": "unsafe-job",
        "ticket_id": "unsafe-ticket",
        "cycle_no": 1,
    }

    with (
        patch.object(worker, "claim_auto_jobs", return_value=[job]),
        patch.object(worker, "retry_auto_job") as retry,
        patch.object(worker, "finalize_auto_job") as finalize,
    ):
        retry.return_value = {
            "job_id": job["job_id"],
            "status": "FAILED",
        }

        worker.process_auto_jobs(
            session_factory=None,
            worker_id="test-worker",
            generate_reply=lambda _: "검증되지 않은 답변",
        )

    finalize.assert_not_called()
