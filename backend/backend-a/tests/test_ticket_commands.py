from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import audit
from app.db import utcnow
from app.model_constraints import idempotency_keys
from app.models import assignments, audit_events, automation_jobs, messages, tickets
from app.seed import stable_id
from tests.conftest import login_as
from tests.test_flow import submit


def action(
    client,
    headers,
    ticket_id,
    operation="reopen",
    *,
    revision=1,
    key="cycle-command-01",
    message="추가 확인을 부탁합니다",
    reason="CUSTOMER_REQUEST",
):
    body = {"expected_revision": revision, "message": message}
    if operation == "request-agent":
        body["reason_code"] = reason
    return client.post(
        f"/api/v1/tickets/{ticket_id}/{operation}", json=body, headers={**headers, "Idempotency-Key": key}
    )


def load_ticket(app, ticket_id):
    with app.state.session_factory() as session:
        return dict(session.execute(select(tickets).where(tickets.c.ticket_id == ticket_id)).mappings().one())


def jobs_for(app, ticket_id):
    with app.state.session_factory() as session:
        return [
            dict(r)
            for r in session.execute(
                select(automation_jobs)
                .where(automation_jobs.c.ticket_id == ticket_id)
                .order_by(automation_jobs.c.cycle_no)
            ).mappings()
        ]


def set_status(app, ticket_id, status, mode="AUTO"):
    with app.state.session_factory.begin() as session:
        session.execute(
            tickets.update()
            .where(tickets.c.ticket_id == ticket_id)
            .values(
                status=status,
                requested_mode=mode,
                resolved_at=utcnow() if status == "RESOLVED" else None,
                resolution_mode=mode if status == "RESOLVED" else None,
            )
        )


@pytest.mark.parametrize("operation", ["reopen", "request-agent"])
def test_customer_action_ownership_and_auth(client, headers, app, operation):
    ticket_id = submit(client, headers).json()["ticket_id"]
    assert action(client, {}, ticket_id, operation).status_code == 401
    assert action(client, login_as(client, "customer2"), ticket_id, operation).status_code == 404
    assert action(client, headers, str(uuid4()), operation).status_code == 404
    assert action(client, login_as(client, "agent"), ticket_id, operation).status_code == 403
    result = action(client, headers, ticket_id, operation)
    assert result.status_code == 201, result.text
    assert result.json()["revision"] == result.json()["cycle_no"] == 2
    assert "lease_token" not in result.text and "reason_code" not in result.text
    detail = client.get(f"/api/v1/tickets/{ticket_id}", headers=headers).json()
    assert detail["revision"] == detail["cycle_no"] == 2
    assert detail["messages"][-1]["body"] == "추가 확인을 부탁합니다"
    with app.state.session_factory() as session:
        assert len(session.execute(select(audit_events).where(audit_events.c.result == "DENIED")).all()) == 4


@pytest.mark.parametrize(
    "status,human",
    [
        ("OPEN", False),
        ("PROCESSING", False),
        ("WAITING_CUSTOMER", False),
        ("RESOLVED", False),
        ("HANDOFF_PENDING", True),
        ("ASSIGNED", True),
        ("IN_PROGRESS", True),
        ("FOLLOWUP_PENDING", True),
    ],
)
def test_reopen_allowed_states(client, headers, app, status, human):
    ticket_id = submit(client, headers).json()["ticket_id"]
    set_status(app, ticket_id, status)
    response = action(client, headers, ticket_id)
    assert response.status_code == 201
    assert response.json()["handling_mode"] == ("HUMAN" if human else "AUTOMATED")
    t = load_ticket(app, ticket_id)
    assert t["status"] == ("HANDOFF_PENDING" if human else "OPEN")
    assert t["resolved_at"] is None and t["resolution_mode"] is None
    assert jobs_for(app, ticket_id)[-1]["job_kind"] == ("HANDOFF" if human else "AUTO")


@pytest.mark.parametrize("status", ["OPEN", "PROCESSING", "WAITING_CUSTOMER", "RESOLVED"])
def test_direct_agent_allowed_states(client, headers, app, status):
    ticket_id = submit(client, headers).json()["ticket_id"]
    set_status(app, ticket_id, status)
    response = action(client, headers, ticket_id, "request-agent", reason="DISSATISFIED")
    assert response.status_code == 201
    t = load_ticket(app, ticket_id)
    assert t["status"] == "HANDOFF_PENDING" and t["requested_mode"] == "HUMAN"
    jobs = jobs_for(app, ticket_id)
    assert jobs[0]["status"] == "CANCELLED"
    assert jobs[1]["job_kind"] == "HANDOFF" and jobs[1]["reason_code"] == "DISSATISFIED"
    assert jobs[1]["source_message_id"] is not None


@pytest.mark.parametrize(
    "status", ["HANDOFF_PENDING", "ASSIGNED", "IN_PROGRESS", "FOLLOWUP_PENDING", "WAITING_CUSTOMER"]
)
def test_agent_request_does_not_duplicate_human_work(client, headers, app, status):
    ticket_id = submit(client, headers).json()["ticket_id"]
    action(client, headers, ticket_id, "request-agent")
    set_status(app, ticket_id, status, "HUMAN")
    before = jobs_for(app, ticket_id)
    result = action(client, headers, ticket_id, "request-agent", revision=2, key="another-agent-key")
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "HUMAN_REQUEST_ALREADY_ACTIVE"
    assert jobs_for(app, ticket_id) == before
    assert load_ticket(app, ticket_id)["cycle_no"] == 2


@pytest.mark.parametrize("operation", ["reopen", "request-agent"])
def test_cancelled_and_stale_revision_are_rejected(client, headers, app, operation):
    ticket_id = submit(client, headers).json()["ticket_id"]
    assert (
        action(client, headers, ticket_id, operation, revision=99).json()["error"]["code"]
        == "TICKET_REVISION_CONFLICT"
    )
    set_status(app, ticket_id, "CANCELLED")
    result = action(client, headers, ticket_id, operation)
    assert result.status_code == 409 and result.json()["error"]["code"] == "TICKET_TRANSITION_NOT_ALLOWED"
    assert len(jobs_for(app, ticket_id)) == 1


@pytest.mark.parametrize("operation", ["reopen", "request-agent"])
def test_action_idempotency_and_snapshot_after_later_changes(client, headers, operation):
    ticket_id = submit(client, headers).json()["ticket_id"]
    first = action(client, headers, ticket_id, operation)
    assert first.status_code == 201
    newer = action(client, headers, ticket_id, revision=2, key="later-reopen-key")
    assert newer.status_code == 201
    replay = action(client, headers, ticket_id, operation)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert action(client, headers, ticket_id, operation, message="different").status_code == 409
    assert action(client, headers, ticket_id, operation, revision=3).status_code == 409
    other_operation = "request-agent" if operation == "reopen" else "reopen"
    assert action(client, headers, ticket_id, other_operation).status_code == 409


def test_global_key_namespace_and_per_user_scope(client, headers):
    ticket_id = submit(client, headers, key="shared-create-key").json()["ticket_id"]
    assert action(client, headers, ticket_id, key="shared-create-key").status_code == 409
    assert action(client, headers, ticket_id, key="shared-action-key").status_code == 201
    assert submit(client, headers, key="shared-action-key").status_code == 409
    second_ticket = submit(client, headers, key="second-create-key").json()["ticket_id"]
    assert action(client, headers, second_ticket, key="shared-action-key").status_code == 409
    other = login_as(client, "customer2")
    other_ticket = submit(client, other).json()["ticket_id"]
    assert action(client, other, other_ticket, key="shared-action-key").status_code == 201


def test_agent_reason_is_part_of_idempotent_request(client, headers):
    ticket_id = submit(client, headers).json()["ticket_id"]
    assert action(client, headers, ticket_id, "request-agent").status_code == 201
    assert action(client, headers, ticket_id, "request-agent", reason="OTHER").status_code == 409


@pytest.mark.parametrize("operation", ["reopen", "request-agent"])
def test_customer_cycle_rolls_back_all_writes(client, headers, app, monkeypatch, operation):
    ticket_id = submit(client, headers).json()["ticket_id"]
    with app.state.session_factory.begin() as session:
        session.execute(
            automation_jobs.update()
            .where(automation_jobs.c.ticket_id == ticket_id)
            .values(
                status="RUNNING",
                lease_token=str(uuid4()),
                lease_owner="test-worker",
                lease_until=utcnow() + timedelta(minutes=2),
            )
        )
        session.execute(
            assignments.insert().values(
                assignment_id=str(uuid4()),
                ticket_id=ticket_id,
                cycle_no=1,
                team_id=stable_id("team"),
                agent_id=stable_id("agent"),
                assigned_at=utcnow(),
                reason_code="TEST",
            )
        )

    def snapshot():
        with app.state.session_factory() as session:
            return {
                table.name: [
                    dict(r)
                    for r in session.execute(select(table).where(table.c.ticket_id == ticket_id)).mappings()
                ]
                for table in (tickets, messages, assignments, automation_jobs, idempotency_keys, audit_events)
            }

    before = snapshot()
    original = audit.record

    def fail(*args, **kwargs):
        if args[2] in {"TICKET_REOPENED", "AGENT_REQUESTED"}:
            raise RuntimeError("deliberate failure after cycle, lease, assignment, message, job writes")
        return original(*args, **kwargs)

    monkeypatch.setattr(audit, "record", fail)
    assert action(client, headers, ticket_id, operation).status_code == 500
    assert snapshot() == before


def test_reopen_closes_old_assignment_and_keeps_human_path(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    set_status(app, ticket_id, "RESOLVED", "HUMAN")
    with app.state.session_factory.begin() as session:
        session.execute(
            assignments.insert().values(
                assignment_id=str(uuid4()),
                ticket_id=ticket_id,
                cycle_no=1,
                team_id=stable_id("team"),
                agent_id=stable_id("agent"),
                assigned_at=utcnow(),
                reason_code="TEST",
            )
        )
    assert action(client, headers, ticket_id).json()["handling_mode"] == "HUMAN"
    t = load_ticket(app, ticket_id)
    assert t["team_id"] is None and t["requested_mode"] == "HUMAN"
    with app.state.session_factory() as session:
        assert (
            session.scalar(select(assignments.c.ended_at).where(assignments.c.ticket_id == ticket_id))
            is not None
        )


@pytest.mark.parametrize("same_key", [True, False])
@pytest.mark.parametrize("operation", ["reopen", "request-agent"])
def test_concurrent_customer_commands(client, headers, app, same_key, operation):
    ticket_id = submit(client, headers).json()["ticket_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda i: action(
                    client,
                    headers,
                    ticket_id,
                    operation,
                    key="concurrent-action-0" if same_key else f"concurrent-action-{i}",
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in results) == ([200, 201] if same_key else [201, 409])
    if same_key:
        assert results[0].json() == results[1].json()
    assert load_ticket(app, ticket_id)["cycle_no"] == 2
    assert len(jobs_for(app, ticket_id)) == 2


def test_reopen_and_agent_request_race_then_human_sticks(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda op: action(client, headers, ticket_id, op, key=f"mixed-command-{op}"),
                ["reopen", "request-agent"],
            )
        )
    assert sorted(r.status_code for r in results) == [201, 409]
    t = load_ticket(app, ticket_id)
    if t["requested_mode"] != "HUMAN":
        assert (
            action(
                client, headers, ticket_id, "request-agent", revision=t["version"], key="agent-after-refresh"
            ).status_code
            == 201
        )
    t = load_ticket(app, ticket_id)
    result = action(client, headers, ticket_id, revision=t["version"], key="reopen-after-human")
    assert result.status_code == 201 and result.json()["handling_mode"] == "HUMAN"
    jobs = jobs_for(app, ticket_id)
    assert jobs[-1]["job_kind"] == "HANDOFF"
    assert all(j["status"] == "CANCELLED" for j in jobs[:-1])


@pytest.mark.parametrize(
    "bad",
    [
        {"message": " "},
        {"expected_revision": 0},
        {"expected_revision": None},
        {"role": "ADMIN"},
        {"customer_id": str(uuid4())},
    ],
)
def test_action_validation(client, headers, bad):
    ticket_id = submit(client, headers).json()["ticket_id"]
    result = client.post(
        f"/api/v1/tickets/{ticket_id}/reopen",
        json={"message": "hello", "expected_revision": 1, **bad},
        headers={**headers, "Idempotency-Key": "validation-command"},
    )
    assert result.status_code == 422
