from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.automation.postgres import job_retry


def run_retry(attempt):
    """Run retry logic with a mocked database session."""
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)

    job = {
        "job_id": "job-1",
        "ticket_id": "ticket-1",
        "lease_token": "lease-1",
        "expected_ticket_version": 1,
        "cycle_no": 1,
    }

    ticket = {
        "ticket_id": "ticket-1",
        "cycle_no": 1,
        "version": 1,
        "requested_mode": "AUTO",
        "status": "OPEN",
    }

    current_job = {
        **job,
        "job_kind": "AUTO",
        "lease_owner": "worker-1",
        "automation_generation": 1,
        "attempt": attempt,
    }

    session = MagicMock()

    ticket_result = MagicMock()
    ticket_result.mappings.return_value.one.return_value = ticket

    job_result = MagicMock()
    job_result.mappings.return_value.one_or_none.return_value = current_job

    job_update_result = MagicMock()
    job_update_result.rowcount = 1

    ticket_update_result = MagicMock()
    ticket_update_result.rowcount = 1

    session.execute.side_effect = [
        ticket_result,
        job_result,
        job_update_result,
        ticket_update_result,
        MagicMock(),  # Audit INSERT
    ]

    @contextmanager
    def begin():
        yield session

    session_factory = MagicMock()
    session_factory.begin.side_effect = begin

    with (
        patch.object(job_retry, "assert_automatic_allowed"),
        patch.object(job_retry, "utcnow", return_value=now),
        patch.object(job_retry.random, "uniform", return_value=2.0),
    ):
        result = job_retry.retry_auto_job(
            session_factory,
            job,
            worker_id="worker-1",
            error_code="MOCK_ERROR",
        )

    expected_calls = 5 if attempt >= job_retry.MAX_ATTEMPTS else 3
    assert session.execute.call_count == expected_calls

    update_statement = session.execute.call_args_list[2].args[0]
    params = update_statement.compile().params

    if attempt >= job_retry.MAX_ATTEMPTS:
        ticket_statement = session.execute.call_args_list[3].args[0]
        ticket_params = ticket_statement.compile().params

        assert ticket_params["requested_mode"] == "HUMAN"
        assert ticket_params["status"] == "HANDOFF_PENDING"
        assert ticket_params["version"] == 2
        assert ticket_params["last_error_code"] == "MOCK_ERROR"

        # cycle_no, SLA, Job expected_ticket_version은 변경하지 않음
        assert "cycle_no" not in ticket_params
        assert "sla_due_at" not in ticket_params
        assert "expected_ticket_version" not in params

        audit_statement = session.execute.call_args_list[4].args[0]
        audit_params = audit_statement.compile().params

        assert audit_params["action"] == "AUTO_JOB_FAILED_HANDOFF"
        assert audit_params["actor_service"] == "backend-b"
        assert audit_params["actor_user_id"] is None
        assert audit_params["target_type"] == "TICKET"
        assert audit_params["target_id"] == "ticket-1"
        assert audit_params["ticket_id"] == "ticket-1"
        assert audit_params["cycle_no"] == 1
        assert audit_params["reason_code"] == "MOCK_ERROR"
        assert audit_params["payload"] == {}

    return result, params


def test_first_failure_retries():
    result, params = run_retry(attempt=1)

    assert result["status"] == "RETRY"
    assert result["attempt"] == 1
    assert result["delay_seconds"] == 32.0

    assert params["status"] == "RETRY"
    assert params["error_code"] == "MOCK_ERROR"
    assert params["lease_token"] is None
    assert params["lease_owner"] is None
    assert params["lease_until"] is None


def test_second_failure_retries():
    result, params = run_retry(attempt=2)

    assert result["status"] == "RETRY"
    assert result["attempt"] == 2
    assert result["delay_seconds"] == 62.0


def test_third_failure_is_terminal():
    result, params = run_retry(attempt=3)

    assert result["status"] == "FAILED"
    assert result["attempt"] == 3
    assert result["delay_seconds"] is None

    assert params["status"] == "FAILED"
    assert params["lease_token"] is None
    assert params["lease_owner"] is None
    assert params["lease_until"] is None


@pytest.mark.parametrize("error_code", ["", "x" * 65, None])
def test_invalid_error_code(error_code):
    with pytest.raises(ValueError, match="Invalid error_code"):
        job_retry.retry_auto_job(
            MagicMock(),
            {},
            worker_id="worker-1",
            error_code=error_code,
        )


def test_wrong_worker_rejected():
    job = {
        "job_id": "job-1",
        "ticket_id": "ticket-1",
        "lease_token": "lease-1",
        "expected_ticket_version": 1,
        "cycle_no": 1,
    }

    ticket = {
        "ticket_id": "ticket-1",
        "cycle_no": 1,
        "version": 1,
        "requested_mode": "AUTO",
        "status": "OPEN",
    }

    current_job = {
        **job,
        "job_kind": "AUTO",
        "lease_owner": "another-worker",
        "automation_generation": 1,
        "attempt": 1,
    }

    _assert_context_rejected(job, ticket, current_job)


def test_changed_ticket_version_rejected():
    job = {
        "job_id": "job-1",
        "ticket_id": "ticket-1",
        "lease_token": "lease-1",
        "expected_ticket_version": 1,
        "cycle_no": 1,
    }

    ticket = {
        "ticket_id": "ticket-1",
        "cycle_no": 1,
        "version": 2,
        "requested_mode": "AUTO",
        "status": "OPEN",
    }

    current_job = {
        **job,
        "job_kind": "AUTO",
        "lease_owner": "worker-1",
        "automation_generation": 1,
        "attempt": 1,
    }

    _assert_context_rejected(job, ticket, current_job)


def _assert_context_rejected(job, ticket, current_job):
    session = MagicMock()

    ticket_result = MagicMock()
    ticket_result.mappings.return_value.one.return_value = ticket

    job_result = MagicMock()
    job_result.mappings.return_value.one_or_none.return_value = current_job

    session.execute.side_effect = [ticket_result, job_result]

    @contextmanager
    def begin():
        yield session

    session_factory = MagicMock()
    session_factory.begin.side_effect = begin

    with pytest.raises(RuntimeError, match="JOB_CONTEXT_CHANGED"):
        job_retry.retry_auto_job(
            session_factory,
            job,
            worker_id="worker-1",
            error_code="MOCK_ERROR",
        )

    # 조회 두 번만 수행하고 UPDATE는 실행하지 않아야 한다.
    assert session.execute.call_count == 2


def test_invalid_lease_rejected():
    job = {
        "job_id": "job-1",
        "ticket_id": "ticket-1",
        "lease_token": "expired-lease",
        "expected_ticket_version": 1,
        "cycle_no": 1,
    }

    ticket = {
        "ticket_id": "ticket-1",
        "cycle_no": 1,
        "version": 1,
        "requested_mode": "AUTO",
        "status": "OPEN",
    }

    session = MagicMock()

    ticket_result = MagicMock()
    ticket_result.mappings.return_value.one.return_value = ticket

    # 유효한 Lease 조건에 일치하는 Job이 없는 상황
    job_result = MagicMock()
    job_result.mappings.return_value.one_or_none.return_value = None

    session.execute.side_effect = [ticket_result, job_result]

    @contextmanager
    def begin():
        yield session

    session_factory = MagicMock()
    session_factory.begin.side_effect = begin

    with pytest.raises(RuntimeError, match="JOB_LEASE_INVALID"):
        job_retry.retry_auto_job(
            session_factory,
            job,
            worker_id="worker-1",
            error_code="MOCK_ERROR",
        )

    # UPDATE 없이 조회 두 번만 실행
    assert session.execute.call_count == 2


def test_automation_paused_rejected():
    job = {
        "job_id": "job-1",
        "ticket_id": "ticket-1",
        "lease_token": "lease-1",
        "expected_ticket_version": 1,
        "cycle_no": 1,
    }

    ticket = {
        "ticket_id": "ticket-1",
        "cycle_no": 1,
        "version": 1,
        "requested_mode": "AUTO",
        "status": "OPEN",
    }

    current_job = {
        **job,
        "job_kind": "AUTO",
        "lease_owner": "worker-1",
        "automation_generation": 1,
        "attempt": 1,
    }

    session = MagicMock()

    ticket_result = MagicMock()
    ticket_result.mappings.return_value.one.return_value = ticket

    job_result = MagicMock()
    job_result.mappings.return_value.one_or_none.return_value = current_job

    session.execute.side_effect = [ticket_result, job_result]

    @contextmanager
    def begin():
        yield session

    session_factory = MagicMock()
    session_factory.begin.side_effect = begin

    with patch.object(
        job_retry,
        "assert_automatic_allowed",
        side_effect=RuntimeError("AUTOMATION_PAUSED"),
    ):
        with pytest.raises(RuntimeError, match="AUTOMATION_PAUSED"):
            job_retry.retry_auto_job(
                session_factory,
                job,
                worker_id="worker-1",
                error_code="MOCK_ERROR",
            )

    # 티켓과 Job 조회만 실행하고 UPDATE는 실행하지 않아야 함
    assert session.execute.call_count == 2


def test_terminal_failure_ticket_conflict():
    job = {
        "job_id": "job-1",
        "ticket_id": "ticket-1",
        "lease_token": "lease-1",
        "expected_ticket_version": 1,
        "cycle_no": 1,
    }

    ticket = {
        "ticket_id": "ticket-1",
        "cycle_no": 1,
        "version": 1,
        "requested_mode": "AUTO",
        "status": "OPEN",
    }

    current_job = {
        **job,
        "job_kind": "AUTO",
        "lease_owner": "worker-1",
        "automation_generation": 1,
        "attempt": 3,
    }

    session = MagicMock()

    ticket_result = MagicMock()
    ticket_result.mappings.return_value.one.return_value = ticket

    job_result = MagicMock()
    job_result.mappings.return_value.one_or_none.return_value = current_job

    job_update_result = MagicMock()
    job_update_result.rowcount = 1

    # Ticket UPDATE 대상이 없어서 충돌한 상황
    ticket_update_result = MagicMock()
    ticket_update_result.rowcount = 0

    session.execute.side_effect = [
        ticket_result,
        job_result,
        job_update_result,
        ticket_update_result,
    ]

    @contextmanager
    def begin():
        yield session

    session_factory = MagicMock()
    session_factory.begin.side_effect = begin

    with (
        patch.object(job_retry, "assert_automatic_allowed"),
        patch.object(job_retry, "utcnow"),
    ):
        with pytest.raises(RuntimeError, match="TICKET_HANDOFF_CONFLICT"):
            job_retry.retry_auto_job(
                session_factory,
                job,
                worker_id="worker-1",
                error_code="MOCK_ERROR",
            )

    assert session.execute.call_count == 4
