from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event

import pytest
from sqlalchemy import select, text

from app import followups, repository
from app.errors import APIError
from app.finalization import WorkRejected, commit_automatic_reply
from app.followup_schemas import FollowupCreate
from app.model_constraints import user_team_scopes
from app.models import followup_actions, tickets
from app.resolution import lock_resolution_gate
from app.seed import stable_id
from tests.conftest import login_as
from tests.phase3_helpers import (
    assign,
    change_state,
    create_followup,
    followup_detail,
    make_ticket,
    staff_user,
)
from tests.test_finalization_contract import lease_reply, wait_for_blocker
from tests.test_ticket_commands import action


def test_prior_mandatory_action_survives_reopen_and_requires_takeover(client, headers, app):
    tid = make_ticket(client, headers, app)
    old, admin = login_as(client, "agent"), login_as(client, "admin")
    aid = create_followup(client, old, tid).json()["action_id"]
    staff_user(app, "agent-new")
    assert action(client, headers, tid).status_code == 201
    assert followup_detail(client, old, aid).status_code == 404
    queue = client.get("/api/v1/staff/followups?status=OPEN", headers=admin).json()["items"]
    assert len(queue) == 1 and queue[0]["needs_handover"]
    assert queue[0]["cycle_no"] == queue[0]["responsibility_cycle_no"] == 1
    assign(app, tid, agent="agent-new", cycle=2)
    new = login_as(client, "agent-new")
    assert followup_detail(client, new, aid).status_code == 200
    assert change_state(client, new, aid, "DONE").status_code == 409
    with pytest.raises(WorkRejected, match="BLOCKING_FOLLOWUP"), app.state.session_factory.begin() as session:
        lock_resolution_gate(
            session,
            tid,
            expected_revision=2,
            cycle_no=2,
            mode="HUMAN",
            human_user=repository.get_user(session, stable_id("agent-new")),
        )
    takeover = client.patch(
        f"/api/v1/staff/followups/{aid}",
        headers=new,
        json={"expected_revision": 1, "owner_user_id": stable_id("agent-new")},
    )
    assert takeover.status_code == 200
    assert takeover.json()["cycle_no"] == 1 and takeover.json()["responsibility_cycle_no"] == 2
    assert takeover.json()["origin_team_id"] == stable_id("team")
    assert not takeover.json()["needs_handover"]
    assert change_state(client, new, aid, "DONE", 2).status_code == 200
    with app.state.session_factory.begin() as session:
        ticket = lock_resolution_gate(
            session,
            tid,
            expected_revision=2,
            cycle_no=2,
            mode="HUMAN",
            human_user=repository.get_user(session, stable_id("agent-new")),
        )
        assert ticket["status"] == "IN_PROGRESS"  # Gate never auto-resolves a ticket.
    assert followup_detail(client, old, aid).status_code == 404


def test_cross_team_takeover_requires_both_admin_scopes(client, headers, app):
    tid = make_ticket(client, headers, app)
    agent, admin = login_as(client, "agent"), login_as(client, "admin")
    aid = create_followup(client, agent, tid).json()["action_id"]
    team_b = stable_id("team-b")
    staff_user(app, "agent-b", team_id=team_b)
    staff_user(app, "admin-b", "ADMIN", team_b)
    assert action(client, headers, tid).status_code == 201
    assign(app, tid, agent="agent-b", team_id=team_b, cycle=2)
    other = login_as(client, "agent-b")
    assert followup_detail(client, other, aid).status_code == 404
    assert followup_detail(client, admin, aid).status_code == 200  # Responsibility queue, not ticket access.
    assert client.get(f"/api/v1/tickets/{tid}", headers=admin).status_code == 404
    payload = {"expected_revision": 1, "owner_team_id": team_b, "owner_user_id": stable_id("agent-b")}
    assert client.patch(f"/api/v1/staff/followups/{aid}", headers=admin, json=payload).status_code == 404
    with app.state.session_factory.begin() as session:
        session.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=team_b))
    moved = client.patch(f"/api/v1/staff/followups/{aid}", headers=admin, json=payload)
    assert moved.status_code == 200 and moved.json()["origin_team_id"] == stable_id("team")
    assert moved.json()["responsibility_cycle_no"] == 2 and moved.json()["cycle_no"] == 1
    assert followup_detail(client, other, aid).status_code == 200


@pytest.mark.parametrize("mode", ["AUTO", "HUMAN"])
def test_common_resolution_gate_blocks_unowned_prior_cycle_actions(client, headers, app, mode):
    tid = make_ticket(client, headers, app, assigned=False)
    admin = login_as(client, "admin")
    aid = create_followup(client, admin, tid, owner_user_id=None).json()["action_id"]
    if mode == "AUTO":
        command = lease_reply(app, tid)
        with (
            pytest.raises(WorkRejected, match="BLOCKING_FOLLOWUP"),
            app.state.session_factory.begin() as session,
        ):
            commit_automatic_reply(session, command)
    else:
        assign(app, tid, cycle=2)
        with (
            pytest.raises(WorkRejected, match="BLOCKING_FOLLOWUP"),
            app.state.session_factory.begin() as session,
        ):
            lock_resolution_gate(
                session,
                tid,
                expected_revision=1,
                cycle_no=2,
                mode="HUMAN",
                human_user=repository.get_user(session, stable_id("agent")),
            )
    assert followup_detail(client, admin, aid).json()["status"] == "OPEN"


@pytest.mark.postgres
@pytest.mark.parametrize("first_operation", ["followup", "resolve"])
def test_postgres_required_followup_creation_and_resolution_race(client, headers, app, first_operation):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL lock race")
    tid = make_ticket(client, headers, app, assigned=False)
    command = lease_reply(app, tid)
    body = FollowupCreate(
        ticket_id=tid,
        owner_team_id=stable_id("team"),
        owner_user_id=stable_id("admin"),
        kind="CHECK",
        blocks_resolution=True,
    )
    held, release = Event(), Event()
    pid = Queue()

    def run(operation, hold=False):
        try:
            with app.state.session_factory.begin() as session:
                if not hold:
                    pid.put(session.scalar(text("SELECT pg_backend_pid()")))
                if operation == "resolve":
                    commit_automatic_reply(session, command)
                else:
                    followups.create(
                        session,
                        repository.get_user(session, stable_id("admin")),
                        body,
                        "race-followup-create",
                    )
                if hold:
                    held.set()
                    if not release.wait(10):
                        raise TimeoutError("Race not released")
            return "OK"
        except (APIError, WorkRejected) as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, first_operation, True)
        try:
            assert held.wait(5)
            second = pool.submit(run, "resolve" if first_operation == "followup" else "followup")
            wait_for_blocker(app, pid.get(timeout=5))
        finally:
            release.set()
        assert first.result(timeout=10) == "OK"
        assert second.result(timeout=10) == (
            "BLOCKING_FOLLOWUP" if first_operation == "followup" else "TICKET_ALREADY_FINISHED"
        )
    with app.state.session_factory() as session:
        t = session.execute(select(tickets).where(tickets.c.ticket_id == tid)).mappings().one()
        fs = session.execute(select(followup_actions).where(followup_actions.c.ticket_id == tid)).all()
    assert (t["status"] == "RESOLVED") == (first_operation == "resolve")
    assert len(fs) == (1 if first_operation == "followup" else 0)
