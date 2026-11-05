from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.db import utcnow
from backend.app.automation.postgres.assignment import AssignmentRejected
from backend.app.automation.postgres.handoff_finalize import finalize_handoff_job


TICKET_ID = "11111111-1111-4111-8111-111111111111"
AGENT_ID = "22222222-2222-4222-8222-222222222222"
TEAM_ID = "33333333-3333-4333-8333-333333333333"
OTHER_TEAM_ID = "44444444-4444-4444-8444-444444444444"
JOB_ID = "55555555-5555-4555-8555-555555555555"
WORKER_ID = "handoff-worker-1"



def make_context(
    *,
    lease_expired=False,
    lease_owner=WORKER_ID,
    ticket_version=5,
    route_team_id=None,
    update_rowcount=1,
):
    token = uuid4()
    job = {
        "job_id": JOB_ID,
        "ticket_id": TICKET_ID,
        "lease_token": token,
    }
    ticket = {
        "ticket_id": TICKET_ID,
        "cycle_no": 2,
        "version": ticket_version,
        "status": "HANDOFF_PENDING",
        "requested_mode": "HUMAN",
    }
    current_job = {
        "job_id": JOB_ID,
        "ticket_id": TICKET_ID,
        "job_kind": "HANDOFF",
        "status": "RUNNING",
        "lease_token": token,
        "lease_owner": lease_owner,
        "lease_until": utcnow() + timedelta(
            seconds=-60 if lease_expired else 3600
        ),
        "cycle_no": 2,
        "expected_ticket_version": 5,
        "automation_generation": 1,
    }
    agent = {
        "user_id": AGENT_ID,
        "active": True,
        "role": "AGENT",
        "team_id": TEAM_ID,
    }
    route = (
        {
            "team_id": route_team_id,
            "revision": 1,
        }
        if route_team_id is not None
        else None
    )

    session = MagicMock()

    def result(value):
        response = MagicMock()
        response.mappings.return_value.one_or_none.return_value = value
        return response

    update_result = MagicMock()
    update_result.rowcount = update_rowcount

    session.execute.side_effect = [
        result(ticket),
        result(current_job),
        result(agent),
        result(route),
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


def execute(factory, job, worker_id=WORKER_ID):
    return finalize_handoff_job(
        factory,
        job,
        worker_id=worker_id,
        agent_id=AGENT_ID,
    )


def test_handoff_success():
    factory, session, job, state = make_context()

    with (
        patch(
            "backend.app.automation.postgres.handoff_finalize.record_queue_route"
        ) as route_mock,
        patch(
            "backend.app.automation.postgres.handoff_finalize.assign_handoff_ticket",
            return_value={"status": "ASSIGNED"},
        ) as assign_mock,
    ):
        result = execute(factory, job)

    assert result["status"] == "HANDED_OFF"
    assert result["assignment"]["status"] == "ASSIGNED"
    assert state["committed"]
    assert not state["rolled_back"]
    route_mock.assert_called_once()
    assign_mock.assert_called_once()

    route_command = route_mock.call_args.args[2]
    assert route_command.expected_revision == 5
    assert route_command.cycle_no == 2
    assert route_command.expected_route_revision == 0

    update_statement = session.execute.call_args.args[0]
    update_params = update_statement.compile().params
    assert update_params["status"] == "HANDED_OFF"
    assert update_params["lease_token"] is None
    assert update_params["lease_owner"] is None


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"lease_expired": True}, "HANDOFF_LEASE_INVALID"),
        ({"lease_owner": "another-worker"}, "HANDOFF_LEASE_INVALID"),
        ({"ticket_version": 6}, "HANDOFF_CONTEXT_CHANGED"),
        ({"route_team_id": OTHER_TEAM_ID}, "ROUTE_TEAM_MISMATCH"),
    ],
)
def test_handoff_rejected(changes, expected_code):
    factory, session, job, state = make_context(**changes)

    with (
        patch(
            "backend.app.automation.postgres.handoff_finalize.record_queue_route"
        ) as route_mock,
        patch(
            "backend.app.automation.postgres.handoff_finalize.assign_handoff_ticket"
        ) as assign_mock,
        pytest.raises(AssignmentRejected) as exc,
    ):
        execute(factory, job)

    assert exc.value.code == expected_code
    assert state["rolled_back"]
    assert not state["committed"]
    route_mock.assert_not_called()
    assign_mock.assert_not_called()


def test_assignment_failure_rolls_back():
    factory, session, job, state = make_context()

    with (
        patch(
            "backend.app.automation.postgres.handoff_finalize.record_queue_route"
        ) as route_mock,
        patch(
            "backend.app.automation.postgres.handoff_finalize.assign_handoff_ticket",
            side_effect=AssignmentRejected("ACTIVE_ASSIGNMENT_EXISTS"),
        ),
        pytest.raises(AssignmentRejected) as exc,
    ):
        execute(factory, job)

    assert exc.value.code == "ACTIVE_ASSIGNMENT_EXISTS"
    assert state["rolled_back"]
    assert not state["committed"]
    route_mock.assert_called_once()


def test_job_update_conflict_rolls_back():
    factory, session, job, state = make_context(update_rowcount=0)

    with (
        patch(
            "backend.app.automation.postgres.handoff_finalize.record_queue_route"
        ),
        patch(
            "backend.app.automation.postgres.handoff_finalize.assign_handoff_ticket",
            return_value={"status": "ASSIGNED"},
        ),
        pytest.raises(AssignmentRejected) as exc,
    ):
        execute(factory, job)

    assert exc.value.code == "HANDOFF_JOB_CONFLICT"
    assert state["rolled_back"]
    assert not state["committed"]


@pytest.mark.parametrize("generation", [None, 1, 999])
def test_handoff_ignores_auto_generation(generation):
    factory, session, job, state = make_context()

    # HANDOFF?? AUTO generation gate? ???? ???.
    # generation ?? ??? ????? ????? ??.
    responses = list(session.execute.side_effect)
    responses[1].mappings.return_value.one_or_none.return_value[
        "automation_generation"
    ] = generation
    session.execute.side_effect = responses

    with (
        patch(
            "backend.app.automation.postgres.handoff_finalize.record_queue_route"
        ),
        patch(
            "backend.app.automation.postgres.handoff_finalize.assign_handoff_ticket",
            return_value={"status": "ASSIGNED"},
        ),
    ):
        result = execute(factory, job)

    assert result["status"] == "HANDED_OFF"
    assert state["committed"]
    assert not state["rolled_back"]
