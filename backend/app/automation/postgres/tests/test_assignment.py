from unittest.mock import MagicMock, patch

import pytest

from backend.app.automation.postgres.assignment import (
    AssignmentRejected,
    assign_handoff_ticket,
)

TICKET_ID = "11111111-1111-4111-8111-111111111111"
AGENT_ID = "22222222-2222-4222-8222-222222222222"
TEAM_ID = "33333333-3333-4333-8333-333333333333"


def make_session(
    *,
    ticket_version=5,
    ticket_status="HANDOFF_PENDING",
    requested_mode="HUMAN",
    ticket_team_id=TEAM_ID,
    agent_active=True,
    agent_role="AGENT",
    agent_team_id=TEAM_ID,
    team_active=True,
    has_scope=True,
    supports_category=True,
    already_assigned=False,
    update_rowcount=1,
):
    session = MagicMock()

    ticket = {
        "ticket_id": TICKET_ID,
        "version": ticket_version,
        "cycle_no": 2,
        "status": ticket_status,
        "requested_mode": requested_mode,
        "team_id": ticket_team_id,
        "category": "DELIVERY",
    }

    agent = {
        "user_id": AGENT_ID,
        "active": agent_active,
        "role": agent_role,
        "team_id": agent_team_id,
    }

    ticket_result = MagicMock()
    ticket_result.mappings.return_value.first.return_value = ticket

    agent_result = MagicMock()
    agent_result.mappings.return_value.first.return_value = agent

    insert_result = MagicMock()

    update_result = MagicMock()
    update_result.rowcount = update_rowcount

    session.execute.side_effect = [
        ticket_result,
        agent_result,
        insert_result,
        update_result,
    ]

    session.scalar.side_effect = [
        team_active,
        has_scope,
        supports_category,
        already_assigned,
    ]

    return session


def assign(session, expected_revision=5):
    return assign_handoff_ticket(
        session,
        ticket_id=TICKET_ID,
        agent_id=AGENT_ID,
        expected_revision=expected_revision,
    )


def assert_rejected(session, expected_code, expected_revision=5):
    with patch("backend.app.automation.postgres.assignment.audit.record") as audit_mock:
        with pytest.raises(AssignmentRejected) as exc:
            assign(session, expected_revision)

        assert exc.value.code == expected_code
        audit_mock.assert_not_called()


def test_assignment_success():
    session = make_session()

    with patch("backend.app.automation.postgres.assignment.audit.record") as audit_mock:
        result = assign(session)

    assert result["status"] == "ASSIGNED"
    assert result["ticket_id"] == TICKET_ID
    assert result["agent_id"] == AGENT_ID
    assert result["team_id"] == TEAM_ID
    assert result["cycle_no"] == 2
    assert result["ticket_version"] == 6

    assert session.execute.call_count == 4
    audit_mock.assert_called_once()

    audit_kwargs = audit_mock.call_args.kwargs
    assert audit_kwargs["action"] == "HANDOFF_TICKET_ASSIGNED"
    assert audit_kwargs["ticket"] == TICKET_ID
    assert audit_kwargs["service"] == "backend-b"

    insert_statement = session.execute.call_args_list[2].args[0]
    update_statement = session.execute.call_args_list[3].args[0]

    insert_params = insert_statement.compile().params
    update_params = update_statement.compile().params

    assert insert_params["ticket_id"] == TICKET_ID
    assert insert_params["agent_id"] == AGENT_ID
    assert insert_params["team_id"] == TEAM_ID
    assert insert_params["cycle_no"] == 2

    assert update_params["status"] == "ASSIGNED"
    assert update_params["version"] == 6
    assert update_params["team_id"] == TEAM_ID

    assert "cycle_no" not in update_statement._values
    assert "sla_due_at" not in update_statement._values


def test_stale_ticket_revision():
    session = make_session(ticket_version=6)
    assert_rejected(session, "STALE_TICKET_REVISION")


def test_ticket_not_handoff_pending():
    session = make_session(ticket_status="ASSIGNED")
    assert_rejected(session, "TICKET_NOT_HANDOFF_PENDING")


def test_human_handoff_required():
    session = make_session(requested_mode="AUTO")
    assert_rejected(session, "HUMAN_HANDOFF_REQUIRED")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"agent_active": False},
        {"agent_role": "CUSTOMER"},
        {"agent_team_id": None},
    ],
)
def test_agent_not_eligible(kwargs):
    session = make_session(**kwargs)
    assert_rejected(session, "AGENT_NOT_ELIGIBLE")


def test_ticket_team_mismatch():
    session = make_session(ticket_team_id="44444444-4444-4444-8444-444444444444")
    assert_rejected(session, "TICKET_TEAM_MISMATCH")


def test_team_not_active():
    session = make_session(team_active=False)
    assert_rejected(session, "TEAM_NOT_ACTIVE")


def test_agent_team_scope_denied():
    session = make_session(has_scope=False)
    assert_rejected(session, "AGENT_TEAM_SCOPE_DENIED")


def test_team_category_unsupported():
    session = make_session(supports_category=False)
    assert_rejected(session, "TEAM_CATEGORY_UNSUPPORTED")


def test_active_assignment_exists():
    session = make_session(already_assigned=True)
    assert_rejected(session, "ACTIVE_ASSIGNMENT_EXISTS")


def test_ticket_assignment_conflict():
    session = make_session(update_rowcount=0)
    assert_rejected(session, "TICKET_ASSIGNMENT_CONFLICT")


def test_ticket_without_team_can_be_assigned():
    session = make_session(ticket_team_id=None)

    with patch("backend.app.automation.postgres.assignment.audit.record"):
        result = assign(session)

    assert result["team_id"] == TEAM_ID
    assert result["status"] == "ASSIGNED"
