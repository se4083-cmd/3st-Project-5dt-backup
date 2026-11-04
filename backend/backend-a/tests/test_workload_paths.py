"""Unassigned is absence of a valid agent assignment, not a human-only queue."""

import pytest
from sqlalchemy import select

from app.jobs import claim_jobs
from app.models import automation_jobs, tickets
from app.staff_models import automation_control
from tests.phase6_helpers import grant
from tests.test_flow import submit
from tests.test_workload import admin, clock, get, ticket  # noqa: F401 (shared fixed-clock fixture)


@pytest.mark.parametrize("routed", [True, False])
@pytest.mark.usefixtures("clock")
@pytest.mark.parametrize(
    "status,mode,job_status,paused,expected",
    [
        ("OPEN", "AUTO", "PENDING", False, "automatic_path"),
        ("PROCESSING", "AUTO", "PENDING", False, "automatic_path"),
        ("WAITING_CUSTOMER", "AUTO", "PENDING", False, "automatic_path"),
        ("OPEN", "AUTO", "RETRY", False, "automatic_path"),
        ("OPEN", "AUTO", "FAILED", False, "automatic_path"),
        ("OPEN", "AUTO", "PENDING", True, "automatic_path"),
        ("HANDOFF_PENDING", "HUMAN", "PENDING", False, "human_assignment_waiting"),
        ("HANDOFF_PENDING", "HUMAN", "FAILED", True, "human_assignment_waiting"),
        ("HANDOFF_PENDING", "AUTO", "FAILED", False, "unknown"),
        ("OPEN", "HUMAN", "PENDING", False, "unknown"),
        ("IN_PROGRESS", "HUMAN", "PENDING", False, "unknown"),
        ("WAITING_CUSTOMER", "HUMAN", "PENDING", False, "unknown"),
    ],
)
def test_declared_path_is_exclusive_and_same_for_routed_and_unrouted(
    client, app, routed, status, mode, job_status, paused, expected
):
    h = admin(client, app)
    grant(app, "admin", "UNROUTED_QUEUE_READ")
    tid = ticket(app, assigned=False, status=status, routed=routed, failed=True)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(requested_mode=mode))
        s.execute(
            automation_jobs.update().where(automation_jobs.c.ticket_id == tid).values(status=job_status)
        )
        s.execute(automation_control.update().values(paused=paused))
    r = get(client, h, include_unrouted=True)
    counts = r["team_queue"]["unassigned"] if routed else r["unrouted"]
    other = r["unrouted"] if routed else r["team_queue"]["unassigned"]
    assert counts["total"] == 1
    assert counts["by_handling_path"][expected] == 1
    assert sum(counts["by_handling_path"].values()) == counts["total"]
    assert counts["invalid_assignment_count"] == 0
    assert other["total"] == sum(other["by_handling_path"].values()) == 0


@pytest.mark.usefixtures("clock")
def test_invalid_previous_cycle_is_unknown_but_valid_failed_assignment_is_excluded(client, app):
    h = admin(client, app)
    ticket(app, failed=True)
    stale = ticket(app, cycle=2, assignment_cycle=1)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == stale).values(requested_mode="HUMAN"))
    counts = get(client, h)["team_queue"]["unassigned"]
    assert counts["total"] == 1
    assert counts["by_handling_path"] == {"automatic_path": 0, "human_assignment_waiting": 0, "unknown": 1}
    assert counts["invalid_assignment_count"] == 1


@pytest.mark.usefixtures("clock")
def test_stored_terminal_resolution_on_active_ticket_is_unknown(client, app):
    h = admin(client, app)
    tid = ticket(app, assigned=False, status="OPEN")
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(resolution_mode="AUTO"))
    counts = get(client, h)["team_queue"]["unassigned"]
    assert counts["by_handling_path"]["unknown"] == counts["total"] == 1


def test_actual_customer_commands_move_from_auto_to_human_current_cycle(client, app, headers):
    h = admin(client, app)
    grant(app, "admin", "UNROUTED_QUEUE_READ")
    tid = submit(client, headers).json()["ticket_id"]
    assert get(client, h, include_unrouted=True)["unrouted"]["by_handling_path"]["automatic_path"] == 1
    response = client.post(
        f"/api/v1/tickets/{tid}/request-agent",
        headers={**headers, "Idempotency-Key": "path-agent-1"},
        json={"expected_revision": 1, "message": "synthetic request", "reason_code": "CUSTOMER_REQUEST"},
    )
    assert response.status_code == 201
    result = get(client, h, include_unrouted=True)
    assert result["unrouted"]["by_handling_path"]["human_assignment_waiting"] == 1
    assert result["unrouted"]["total"] == 1
    assert (
        client.post(
            f"/api/v1/tickets/{tid}/reopen",
            headers={**headers, "Idempotency-Key": "path-reopen-1"},
            json={"expected_revision": 2, "message": "synthetic continuation"},
        ).status_code
        == 201
    )
    assert (
        get(client, h, include_unrouted=True)["unrouted"]["by_handling_path"]["human_assignment_waiting"] == 1
    )
    with app.state.session_factory() as s:
        jobs = list(
            s.execute(
                select(automation_jobs.c.cycle_no, automation_jobs.c.status)
                .where(automation_jobs.c.ticket_id == tid)
                .order_by(automation_jobs.c.cycle_no)
            )
        )
        assert [row.status for row in jobs] == ["CANCELLED", "CANCELLED", "PENDING"]


@pytest.mark.postgres
def test_actual_auto_claim_and_paused_claim_remain_automatic_path(client, app, headers):
    from tests.test_finalization_contract import require_postgres

    require_postgres(app)
    h = admin(client, app)
    grant(app, "admin", "UNROUTED_QUEUE_READ")
    tid = submit(client, headers).json()["ticket_id"]
    with app.state.session_factory.begin() as s:
        assert claim_jobs(s, "local-path-worker")
    assert get(client, h, include_unrouted=True)["unrouted"]["by_handling_path"]["automatic_path"] == 1
    with app.state.session_factory.begin() as s:
        s.execute(automation_control.update().values(paused=True))
        assert claim_jobs(s, "paused-local-worker") == []
        assert (
            s.scalar(select(automation_jobs.c.status).where(automation_jobs.c.ticket_id == tid)) == "RUNNING"
        )
    assert get(client, h, include_unrouted=True)["unrouted"]["by_handling_path"]["automatic_path"] == 1


@pytest.mark.usefixtures("clock")
def test_mixed_paths_sum_to_total_with_invalid_assignment_as_separate_subset(client, app):
    h = admin(client, app)
    grant(app, "admin", "UNROUTED_QUEUE_READ")
    for routed in (True, False):
        ticket(app, assigned=False, routed=routed, status="OPEN")
        ticket(app, assigned=False, routed=routed, status="PROCESSING")
        human = ticket(app, assigned=False, routed=routed, status="HANDOFF_PENDING")
        unknown = ticket(app, routed=routed, cycle=2, assignment_cycle=1)
        with app.state.session_factory.begin() as s:
            s.execute(
                tickets.update()
                .where(tickets.c.ticket_id.in_([human, unknown]))
                .values(requested_mode="HUMAN")
            )
    r = get(client, h, include_unrouted=True)
    for counts in (r["team_queue"]["unassigned"], r["unrouted"]):
        assert counts["total"] == 4
        assert counts["by_handling_path"] == {
            "automatic_path": 2,
            "human_assignment_waiting": 1,
            "unknown": 1,
        }
        assert sum(counts["by_handling_path"].values()) == counts["total"]
        assert counts["invalid_assignment_count"] == 1
