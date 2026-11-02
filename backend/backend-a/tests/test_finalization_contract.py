from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Queue
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app import audit, repository
from app.db import utcnow
from app.errors import APIError
from app.finalization import AutomaticReply, WorkRejected, commit_automatic_reply
from app.jobs import claim_jobs
from app.models import audit_events, automation_jobs, followup_actions, messages, tickets
from app.schemas import ReopenRequest
from app.seed import stable_id
from app.ticket_commands import change_cycle
from tests.test_flow import submit
from tests.test_ticket_commands import action, jobs_for, load_ticket


def lease_reply(app, ticket_id):
    with app.state.session_factory.begin() as session:
        if app.state.engine.dialect.name == "postgresql":
            claimed = claim_jobs(session, "contract-worker")
            job = next(j for j in claimed if j["ticket_id"] == ticket_id)
        else:
            # SQLite tests exercise the shared storage contract, not row locking.
            job = dict(
                session.execute(
                    select(automation_jobs).where(
                        automation_jobs.c.ticket_id == ticket_id, automation_jobs.c.status == "PENDING"
                    )
                )
                .mappings()
                .one()
            )
            job.update(
                status="RUNNING",
                lease_token=str(uuid4()),
                lease_owner="contract-worker",
                lease_until=utcnow() + timedelta(minutes=1),
            )
            session.execute(
                automation_jobs.update().where(automation_jobs.c.job_id == job["job_id"]).values(**job)
            )
    return AutomaticReply(
        job_id=job["job_id"],
        lease_token=job["lease_token"],
        worker_id="contract-worker",
        cycle_no=job["cycle_no"],
        expected_revision=job["expected_ticket_version"],
        message="B에서 사전 검증된 것으로 가정한 합성 답변",
    )


def finals(app, ticket_id):
    with app.state.session_factory() as session:
        return session.execute(
            select(messages.c.cycle_no, messages.c.message_id).where(
                messages.c.ticket_id == ticket_id, messages.c.final_reply.is_(True)
            )
        ).all()


@pytest.mark.parametrize("operation", ["reopen", "request-agent"])
def test_previous_cycle_reply_rejected_after_customer_command(client, headers, app, operation):
    ticket_id = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, ticket_id)
    assert action(client, headers, ticket_id, operation).status_code == 201
    with (
        pytest.raises(WorkRejected, match="STALE_TICKET_REVISION"),
        app.state.session_factory.begin() as session,
    ):
        commit_automatic_reply(session, command)
    assert finals(app, ticket_id) == []
    old, new = jobs_for(app, ticket_id)
    assert old["status"] == "CANCELLED" and old["lease_token"] is None
    assert new["status"] == "PENDING"


@pytest.mark.parametrize("bad", ["token", "owner", "expired", "revision"])
def test_reply_commit_revalidates_lease_and_version(client, headers, app, bad):
    ticket_id = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, ticket_id)
    changes = {
        "token": {"lease_token": uuid4()},
        "owner": {"worker_id": "different-worker"},
        "revision": {"expected_revision": 99},
    }
    if bad == "expired":
        with app.state.session_factory.begin() as session:
            session.execute(
                automation_jobs.update()
                .where(automation_jobs.c.job_id == str(command.job_id))
                .values(lease_until=utcnow() - timedelta(seconds=1))
            )
    else:
        command = command.model_copy(update=changes[bad])
    with pytest.raises(WorkRejected), app.state.session_factory.begin() as session:
        commit_automatic_reply(session, command)
    assert finals(app, ticket_id) == []


def test_human_path_cannot_commit_automatic_reply_even_for_latest_cycle(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    action(client, headers, ticket_id, "request-agent")
    job = jobs_for(app, ticket_id)[-1]
    token = str(uuid4())
    with app.state.session_factory.begin() as session:
        session.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == job["job_id"])
            .values(
                status="RUNNING",
                lease_owner="handoff-worker",
                lease_token=token,
                lease_until=utcnow() + timedelta(minutes=1),
            )
        )
    command = AutomaticReply(
        job_id=job["job_id"],
        lease_token=token,
        worker_id="handoff-worker",
        cycle_no=2,
        expected_revision=2,
        message="must not be sent automatically",
    )
    with (
        pytest.raises(WorkRejected, match="AUTOMATION_NOT_ALLOWED"),
        app.state.session_factory.begin() as session,
    ):
        commit_automatic_reply(session, command)
    assert finals(app, ticket_id) == []


def test_one_final_per_cycle_and_history_survives_reopen(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    first = lease_reply(app, ticket_id)
    with app.state.session_factory.begin() as session:
        commit_automatic_reply(session, first)
    with pytest.raises(WorkRejected), app.state.session_factory.begin() as session:
        commit_automatic_reply(session, first)
    assert action(client, headers, ticket_id, revision=2).status_code == 201
    assert jobs_for(app, ticket_id)[0]["status"] == "SUCCEEDED"
    second = lease_reply(app, ticket_id)
    with app.state.session_factory.begin() as session:
        commit_automatic_reply(session, second)
    assert [r.cycle_no for r in finals(app, ticket_id)] == [1, 2]
    assert load_ticket(app, ticket_id)["version"] == 4


def test_final_reply_transaction_rolls_back_if_audit_fails(client, headers, app, monkeypatch):
    ticket_id = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, ticket_id)
    before = jobs_for(app, ticket_id)

    def fail(*args, **kwargs):
        raise RuntimeError("deliberate final reply audit failure")

    monkeypatch.setattr(audit, "record", fail)
    with pytest.raises(RuntimeError), app.state.session_factory.begin() as session:
        commit_automatic_reply(session, command)
    assert finals(app, ticket_id) == [] and jobs_for(app, ticket_id) == before
    assert load_ticket(app, ticket_id)["version"] == 1


def test_blocking_followup_prevents_resolution(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, ticket_id)
    with app.state.session_factory.begin() as session:
        session.execute(
            followup_actions.insert().values(
                action_id=str(uuid4()),
                ticket_id=ticket_id,
                cycle_no=1,
                owner_team_id=stable_id("team"),
                kind="TEST",
                status="OPEN",
                blocks_resolution=True,
                version=1,
            )
        )
    with pytest.raises(WorkRejected, match="BLOCKING_FOLLOWUP"), app.state.session_factory.begin() as session:
        commit_automatic_reply(session, command)
    assert finals(app, ticket_id) == []


@pytest.mark.postgres
def test_lease_expiry_is_rechecked_after_ticket_lock_wait(client, headers, app):
    require_postgres(app)
    ticket_id = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, ticket_id)
    pid_queue = Queue()

    def commit():
        try:
            with app.state.session_factory.begin() as session:
                pid_queue.put(session.scalar(text("SELECT pg_backend_pid()")))
                commit_automatic_reply(session, command)
            return "OK"
        except WorkRejected as error:
            return error.code

    with ThreadPoolExecutor(max_workers=1) as pool:
        with app.state.session_factory.begin() as owner:
            owner.execute(select(tickets).where(tickets.c.ticket_id == ticket_id).with_for_update()).one()
            future = pool.submit(commit)
            wait_for_blocker(app, pid_queue.get(timeout=5))
            # Expiry is after function entry, before its ticket/job locks are obtained.
            owner.execute(
                automation_jobs.update()
                .where(automation_jobs.c.job_id == str(command.job_id))
                .values(lease_until=utcnow())
            )
        assert future.result(timeout=10) == "INVALID_LEASE"
    assert finals(app, ticket_id) == []


def require_postgres(app):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL locks required; SQLite is not race verification")


def wait_for_blocker(app, pid):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        with app.state.engine.connect() as connection:
            if connection.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pid}) > 0:
                return
        sleep(0.02)
    raise AssertionError("Expected an actual PostgreSQL row-lock wait")


@pytest.mark.postgres
@pytest.mark.parametrize("first_operation", ["reopen", "commit"])
def test_postgres_final_reply_and_reopen_race_both_lock_orders(client, headers, app, first_operation):
    require_postgres(app)
    ticket_id = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, ticket_id)
    written, release = Event(), Event()
    second_pid = Queue()

    def run(operation, hold=False):
        try:
            with app.state.session_factory.begin() as session:
                pid = session.scalar(text("SELECT pg_backend_pid()"))
                if not hold:
                    second_pid.put(pid)
                if operation == "commit":
                    commit_automatic_reply(session, command)
                else:
                    user = repository.get_user(session, stable_id("customer1"))
                    change_cycle(
                        session,
                        user,
                        ticket_id,
                        ReopenRequest(expected_revision=1, message="race reopen"),
                        "race-reopen-key",
                        operation="REOPEN",
                    )
                if hold:
                    written.set()
                    if not release.wait(10):
                        raise TimeoutError("Lock test was not released")
            return "OK"
        except (APIError, WorkRejected) as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, first_operation, True)
        try:
            assert written.wait(5)
            second = pool.submit(run, "commit" if first_operation == "reopen" else "reopen")
            wait_for_blocker(app, second_pid.get(timeout=5))
        finally:
            release.set()
        assert first.result(timeout=10) == "OK"
        assert second.result(timeout=10) == (
            "STALE_TICKET_REVISION" if first_operation == "reopen" else "TICKET_REVISION_CONFLICT"
        )
    assert len(finals(app, ticket_id)) == (0 if first_operation == "reopen" else 1)
    if first_operation == "commit":
        assert action(client, headers, ticket_id, revision=2).status_code == 201
    assert load_ticket(app, ticket_id)["cycle_no"] == 2


@pytest.mark.postgres
def test_postgres_duplicate_final_reply_race(client, headers, app):
    require_postgres(app)
    ticket_id = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, ticket_id)

    def commit():
        try:
            with app.state.session_factory.begin() as session:
                commit_automatic_reply(session, command)
            return "OK"
        except WorkRejected as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: commit(), range(2)))
    assert sorted(results) == ["OK", "STALE_TICKET_REVISION"]
    assert len(finals(app, ticket_id)) == 1


@pytest.mark.postgres
def test_postgres_handoff_claim_is_separate_from_automation(client, headers, app):
    require_postgres(app)
    ticket_id = submit(client, headers).json()["ticket_id"]
    assert action(client, headers, ticket_id, "request-agent").status_code == 201
    with app.state.session_factory.begin() as session:
        assert claim_jobs(session, "automatic-worker") == []
        handoff = claim_jobs(session, "human-routing-worker", job_kind="HANDOFF")
        assert len(handoff) == 1 and handoff[0]["cycle_no"] == 2
    with app.state.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_events)
                .where(audit_events.c.action == "AGENT_REQUESTED", audit_events.c.ticket_id == ticket_id)
            )
            == 1
        )
