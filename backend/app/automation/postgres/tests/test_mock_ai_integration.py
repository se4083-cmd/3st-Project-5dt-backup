"""Fixture Gate -> Worker handoff integration test."""

from unittest.mock import patch

from backend.app.automation.postgres import worker
from backend.app.automation.postgres.mock_ai_provider import generate_mock_reply


def test_inactive_rule_requests_immediate_handoff():
    job = {
        "job_id": "mock-job-1",
        "ticket_id": "f3fc8c61-5b47-50c9-b0ca-840f40fbc6a7",
        "cycle_no": 1,
    }

    with (
        patch.object(worker, "claim_auto_jobs", return_value=[job]),
        patch.object(worker, "retry_auto_job") as retry,
        patch.object(worker, "finalize_auto_job") as finalize,
    ):
        retry.return_value = {
            "job_id": job["job_id"],
            "status": "HANDOFF_PENDING",
        }

        results = worker.process_auto_jobs(
            session_factory=None,
            worker_id="mock-worker",
            generate_reply=generate_mock_reply,
        )

    retry.assert_called_once_with(
        None,
        job,
        worker_id="mock-worker",
        error_code="AUTOMATION_RULE_INACTIVE",
        force_handoff=True,
    )
    finalize.assert_not_called()
    assert results[0]["status"] == "HANDOFF_PENDING"


def test_approved_mock_reply_reaches_finalize():
    from backend.app.automation.postgres import mock_ai_provider

    job = {
        "job_id": "mock-job-approved",
        "ticket_id": "mock-ticket-approved",
        "cycle_no": 1,
    }

    suggestion = {
        "ticket_id": job["ticket_id"],
        "cycle_no": 1,
        "revision": 1,
        "suggestion_id": "suggestion-approved",
        "rule_id": "rule-approved",
        "draft": "검증된 Mock 고객 안내 답변입니다.",
        "evidence_refs": [{"document_id": "policy-test"}],
    }

    gate_result = {
        "allowed": True,
        "reason": "GATE_PASSED",
        "suggestion_id": "suggestion-approved",
        "rule_id": "rule-approved",
    }

    with (
        patch.object(worker, "claim_auto_jobs", return_value=[job]),
        patch.object(mock_ai_provider, "load_json", return_value=[suggestion]),
        patch.object(mock_ai_provider, "evaluate_gate", return_value=gate_result),
        patch.object(worker, "retry_auto_job") as retry,
        patch.object(worker, "finalize_auto_job") as finalize,
    ):
        results = worker.process_auto_jobs(
            session_factory=None,
            worker_id="mock-worker",
            generate_reply=mock_ai_provider.generate_mock_reply,
        mock_mode=True,
        )

    finalize.assert_called_once_with(
        None,
        job,
        suggestion["draft"],
        "mock-worker",
    )
    retry.assert_not_called()
    assert results[0]["status"] == "SUCCEEDED"
