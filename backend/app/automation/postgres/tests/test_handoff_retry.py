from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.db import utcnow
from backend.app.automation.postgres.handoff_retry import retry_handoff_job


JOB_ID = "55555555-5555-4555-8555-555555555555"
TICKET_ID = "11111111-1111-4111-8111-111111111111"
WORKER_ID = "handoff-worker-1"



def make_context(*, attempt=1, lease_owner=WORKER_ID,
                 ticket_version=5, update_rowcount=1):
    token = uuid4()
    job = {
        "job_id": JOB_ID,
        "ticket_id": TICKET_ID,
        "lease_token": token,
        "expected_ticket_version": 5,
        "cycle_no": 2,
    }

    ticket = {
        "ticket_id": TICKET_ID,
        "version": ticket_version,
        "cycle_no": 2,
        "requested_mode": "HUMAN",
        "status": "HANDOFF_PENDING",
    }

    current_job = {
        **job,
        "job_kind": "HANDOFF",
        "status": "RUNNING",
        "lease_owner": lease_owner,
        "lease_until": utcnow() + timedelta(hours=1),
        "attempt": attempt,
        "automation_generation": 1,
    }

    session = MagicMock()

    def result(value, *, many=False):
        response = MagicMock()
        mappings = response.mappings.return_value
        mappings.one.return_value = value
        mappings.one_or_none.return_value = value
        return response

    update_result = MagicMock()
    update_result.rowcount = update_rowcount

    session.execute.side_effect = [
        result(ticket),
        result(current_job),
        update_result,
    ]

    state = {"committed": False, "rolled_back": False}

    @contextmanager
    def transaction():
        try:
            yield session
        except Exception:
            state["rolled_back"] = True
            raise
        else:
            state["committed"] = True

    factory = MagicMock()
    factory.begin.side_effect = transaction

    return factory, session, job, state


@pytest.mark.parametrize(
    ("attempt", "expected_status", "expected_delay"),
    [
        (1, "RETRY", 30),
        (2, "RETRY", 60),
        (3, "FAILED", None),
    ],
)
def test_retry_policy(attempt, expected_status, expected_delay):
    factory, session, job, state = make_context(attempt=attempt)

    with patch(
        "backend.app.automation.postgres.handoff_retry.random.uniform",
        return_value=0,
    ):
        result = retry_handoff_job(
            factory, job, WORKER_ID, "NO_ELIGIBLE_AGENT"
        )

    assert result["status"] == expected_status
    assert result["delay_seconds"] == expected_delay
    assert state["committed"]
    assert not state["rolled_back"]

    update_statement = session.execute.call_args.args[0]
    values = update_statement.compile().params

    assert values["status"] == expected_status
    assert values["error_code"] == "NO_ELIGIBLE_AGENT"
    assert values["lease_token"] is None
    assert values["lease_owner"] is None
    assert values["lease_until"] is None

    assert session.execute.call_count == 3


@pytest.mark.parametrize(
    ("changes", "expected_error"),
    [
        ({"lease_owner": "another-worker"}, "HANDOFF_CONTEXT_CHANGED"),
        ({"ticket_version": 6}, "HANDOFF_CONTEXT_CHANGED"),
        ({"update_rowcount": 0}, "HANDOFF_LEASE_CHANGED"),
    ],
)
def test_rejected_and_rolled_back(changes, expected_error):
    factory, session, job, state = make_context(**changes)

    with pytest.raises(RuntimeError, match=expected_error):
        retry_handoff_job(factory, job, WORKER_ID, "NO_ELIGIBLE_AGENT")

    assert state["rolled_back"]
    assert not state["committed"]


@pytest.mark.parametrize("error_code", ["", "x" * 65, None])
def test_invalid_error_code(error_code):
    factory, session, job, state = make_context()

    with pytest.raises(ValueError, match="INVALID_ERROR_CODE"):
        retry_handoff_job(factory, job, WORKER_ID, error_code)

    factory.begin.assert_not_called()


@pytest.mark.parametrize("generation", [None, 1, 999])
def test_handoff_retry_ignores_auto_generation(generation):
    factory, session, job, state = make_context()
    responses = list(session.execute.side_effect)
    responses[1].mappings.return_value.one_or_none.return_value[
        "automation_generation"
    ] = generation
    session.execute.side_effect = responses

    result = retry_handoff_job(
        factory, job, WORKER_ID, "NO_ELIGIBLE_AGENT"
    )

    assert result["status"] == "RETRY"
    assert state["committed"]
    assert not state["rolled_back"]
