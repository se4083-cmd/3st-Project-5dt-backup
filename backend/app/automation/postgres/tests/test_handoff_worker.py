from unittest.mock import patch

import pytest

from backend.app.automation.postgres.handoff_worker import process_handoff_jobs


JOB_ID = "55555555-5555-4555-8555-555555555555"
AGENT_ID = "22222222-2222-4222-8222-222222222222"
WORKER_ID = "handoff-worker-1"

CLAIM = "backend.app.automation.postgres.handoff_worker.claim_handoff_jobs"
FINALIZE = "backend.app.automation.postgres.handoff_worker.finalize_handoff_job"


def test_success():
    job = {"job_id": JOB_ID}

    with (
        patch(CLAIM, return_value=[job]) as claim,
        patch(
            FINALIZE,
            return_value={"job_id": JOB_ID, "status": "HANDED_OFF"},
        ) as finalize,
    ):
        results = process_handoff_jobs(
            object(),
            WORKER_ID,
            select_agent=lambda item: AGENT_ID,
        )

    assert results == [{"job_id": JOB_ID, "status": "HANDED_OFF"}]
    claim.assert_called_once()
    finalize.assert_called_once()
    assert finalize.call_args.kwargs["agent_id"] == AGENT_ID


def test_no_eligible_agent():
    retry_path = (
        "backend.app.automation.postgres.handoff_worker.retry_handoff_job"
    )

    with (
        patch(CLAIM, return_value=[{"job_id": JOB_ID}]),
        patch(FINALIZE) as finalize,
        patch(
            retry_path,
            return_value={
                "job_id": JOB_ID,
                "status": "RETRY",
                "attempt": 1,
                "delay_seconds": 30,
            },
        ) as retry,
    ):
        results = process_handoff_jobs(
            object(),
            WORKER_ID,
            select_agent=lambda item: None,
        )

    assert results[0]["status"] == "RETRY"
    assert results[0]["attempt"] == 1
    finalize.assert_not_called()
    retry.assert_called_once()
    assert retry.call_args.kwargs["worker_id"] == WORKER_ID
    assert retry.call_args.kwargs["error_code"] == "NO_ELIGIBLE_AGENT"


def test_finalization_failure():
    with (
        patch(CLAIM, return_value=[{"job_id": JOB_ID}]),
        patch(FINALIZE, side_effect=RuntimeError("DB_ERROR")),
    ):
        results = process_handoff_jobs(
            object(),
            WORKER_ID,
            select_agent=lambda item: AGENT_ID,
        )

    assert results[0]["status"] == "FINALIZATION_FAILED"


@pytest.mark.parametrize(
    ("worker_id", "selector", "limit"),
    [
        ("", lambda job: AGENT_ID, 10),
        (WORKER_ID, None, 10),
        (WORKER_ID, lambda job: AGENT_ID, 0),
        (WORKER_ID, lambda job: AGENT_ID, 11),
    ],
)
def test_invalid_arguments(worker_id, selector, limit):
    with patch(CLAIM) as claim:
        with pytest.raises(ValueError):
            process_handoff_jobs(
                object(),
                worker_id,
                select_agent=selector,
                limit=limit,
            )

    claim.assert_not_called()


@pytest.mark.parametrize(
    "error_code",
    ["AUTOMATION_PAUSED", "AUTOMATION_GENERATION_CHANGED"],
)
def test_control_rejection_does_not_stop_handoff_batch(error_code):
    from app.resolution import WorkRejected

    jobs = [
        {"job_id": JOB_ID},
        {"job_id": "66666666-6666-4666-8666-666666666666"},
    ]

    with (
        patch(CLAIM, return_value=jobs),
        patch(FINALIZE, side_effect=WorkRejected(error_code)) as finalize,
    ):
        results = process_handoff_jobs(
            object(),
            WORKER_ID,
            select_agent=lambda item: AGENT_ID,
        )

    assert len(results) == 2
    assert [item["job_id"] for item in results] == [
        job["job_id"] for job in jobs
    ]
    assert all(
        item["status"] == "FINALIZATION_FAILED"
        for item in results
    )
    assert finalize.call_count == 2


@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    [
        ("HANDOFF_LEASE_INVALID", "LEASE_INVALID"),
        ("HANDOFF_CONTEXT_CHANGED", "CONTEXT_CHANGED"),
    ],
)
def test_invalid_handoff_is_not_retried(error_code, expected_status):
    from backend.app.automation.postgres.assignment import AssignmentRejected

    job = {"job_id": JOB_ID}
    retry_path = (
        "backend.app.automation.postgres.handoff_worker.retry_handoff_job"
    )

    with (
        patch(CLAIM, return_value=[job]),
        patch(
            FINALIZE,
            side_effect=AssignmentRejected(error_code),
        ) as finalize,
        patch(retry_path) as retry,
    ):
        results = process_handoff_jobs(
            object(),
            WORKER_ID,
            select_agent=lambda item: AGENT_ID,
        )

    assert results == [{
        "job_id": JOB_ID,
        "status": expected_status,
    }]
    finalize.assert_called_once()
    retry.assert_not_called()


def test_agent_selection_exception_is_not_misclassified():
    retry_path = (
        "backend.app.automation.postgres.handoff_worker.retry_handoff_job"
    )

    def broken_selector(job):
        raise RuntimeError("DB_CONNECTION_ERROR")

    with (
        patch(CLAIM, return_value=[{"job_id": JOB_ID}]),
        patch(FINALIZE) as finalize,
        patch(
            retry_path,
            return_value={
                "job_id": JOB_ID,
                "status": "RETRY",
                "attempt": 1,
                "delay_seconds": 30,
            },
        ) as retry,
    ):
        results = process_handoff_jobs(
            object(),
            WORKER_ID,
            select_agent=broken_selector,
        )

    assert results[0]["status"] == "RETRY"
    assert retry.call_args.kwargs["error_code"] == "AGENT_SELECTION_ERROR"
    finalize.assert_not_called()


@pytest.mark.parametrize(
    "error_code",
    ["AUTOMATION_PAUSED", "AUTOMATION_GENERATION_CHANGED"],
)
def test_retry_rejection_does_not_stop_handoff_batch(error_code):
    from app.resolution import WorkRejected

    jobs = [
        {"job_id": JOB_ID},
        {"job_id": "66666666-6666-4666-8666-666666666666"},
    ]

    retry_path = (
        "backend.app.automation.postgres.handoff_worker.retry_handoff_job"
    )

    with (
        patch(CLAIM, return_value=jobs),
        patch(
            retry_path,
            side_effect=WorkRejected(error_code),
        ) as retry,
        patch(FINALIZE) as finalize,
    ):
        results = process_handoff_jobs(
            object(),
            WORKER_ID,
            select_agent=lambda job: None,
        )

    assert results == [
        {"job_id": job["job_id"], "status": "RETRY_RECORD_FAILED"}
        for job in jobs
    ]
    assert retry.call_count == 2
    finalize.assert_not_called()
