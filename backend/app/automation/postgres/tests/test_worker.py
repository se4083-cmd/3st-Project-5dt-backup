from unittest.mock import MagicMock, patch

import pytest

from backend.app.automation.postgres import worker


@pytest.fixture
def job():
    return {
        "job_id": "job-1",
        "ticket_id": "ticket-1",
        "lease_token": "lease-1",
        "expected_ticket_version": 1,
        "cycle_no": 1,
        "automation_generation": 1,
    }


def test_worker_success(job):
    session_factory = MagicMock()

    with (
        patch.object(worker, "claim_auto_jobs", return_value=[job]),
        patch.object(worker, "finalize_auto_job") as finalize,
        patch.object(worker, "retry_auto_job") as retry,
    ):
        results = worker.process_auto_jobs(
            session_factory,
            worker_id="worker-1",
            generate_reply=lambda _: "승인된 답변입니다.",
        )

        assert results == [{"job_id": "job-1", "status": "SUCCEEDED"}]
        finalize.assert_called_once_with(
            session_factory,
            job,
            "승인된 답변입니다.",
            "worker-1",
        )
        retry.assert_not_called()


def test_worker_generation_failure(job):
    session_factory = MagicMock()

    def fail_generation(_):
        raise RuntimeError("AI unavailable")

    with (
        patch.object(worker, "claim_auto_jobs", return_value=[job]),
        patch.object(
            worker,
            "retry_auto_job",
            return_value={"job_id": "job-1", "status": "RETRY"},
        ) as retry,
        patch.object(worker, "finalize_auto_job") as finalize,
    ):
        results = worker.process_auto_jobs(
            session_factory,
            worker_id="worker-1",
            generate_reply=fail_generation,
        )

        assert results[0]["status"] == "RETRY"
        retry.assert_called_once_with(
            session_factory,
            job,
            worker_id="worker-1",
            error_code="REPLY_GENERATION_FAILED",
        )
        finalize.assert_not_called()


def test_worker_empty_reply(job):
    session_factory = MagicMock()

    with (
        patch.object(worker, "claim_auto_jobs", return_value=[job]),
        patch.object(
            worker,
            "retry_auto_job",
            return_value={"job_id": "job-1", "status": "RETRY"},
        ) as retry,
    ):
        results = worker.process_auto_jobs(
            session_factory,
            worker_id="worker-1",
            generate_reply=lambda _: "   ",
        )

        assert results[0]["status"] == "RETRY"
        retry.assert_called_once()


def test_worker_finalize_failure(job):
    session_factory = MagicMock()

    with (
        patch.object(worker, "claim_auto_jobs", return_value=[job]),
        patch.object(
            worker,
            "finalize_auto_job",
            side_effect=RuntimeError("DB failure"),
        ),
        patch.object(worker, "retry_auto_job") as retry,
    ):
        results = worker.process_auto_jobs(
            session_factory,
            worker_id="worker-1",
            generate_reply=lambda _: "답변",
        )

        assert results == [{"job_id": "job-1", "status": "FINALIZATION_FAILED"}]
        retry.assert_not_called()


def test_worker_retry_record_failure(job):
    session_factory = MagicMock()

    def fail_generation(_):
        raise RuntimeError("AI unavailable")

    with (
        patch.object(worker, "claim_auto_jobs", return_value=[job]),
        patch.object(
            worker,
            "retry_auto_job",
            side_effect=RuntimeError("DB failure"),
        ),
    ):
        results = worker.process_auto_jobs(
            session_factory,
            worker_id="worker-1",
            generate_reply=fail_generation,
        )

        assert results == [{"job_id": "job-1", "status": "RETRY_RECORD_FAILED"}]


def test_worker_no_jobs():
    session_factory = MagicMock()

    with patch.object(worker, "claim_auto_jobs", return_value=[]):
        results = worker.process_auto_jobs(
            session_factory,
            worker_id="worker-1",
            generate_reply=lambda _: "답변",
        )

        assert results == []
