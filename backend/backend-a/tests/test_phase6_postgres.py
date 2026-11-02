from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app import repository
from app.automation_control import StopCommand, change
from app.db import build_engine, session_factory
from app.errors import APIError
from app.finalization import WorkRejected, commit_automatic_reply
from app.jobs import claim_jobs
from app.models import automation_jobs, automation_rules, messages
from app.seed import seed_fixture, stable_id
from app.staff_models import automation_control, automation_control_history, staff_permissions
from tests.conftest import ROOT, login_as, migrate
from tests.phase6_helpers import BASE, grant
from tests.test_automation_control import resume, stop
from tests.test_finalization_contract import lease_reply, require_postgres, wait_for_blocker
from tests.test_flow import submit
from tests.test_ticket_commands import action


@pytest.mark.postgres
def test_pause_blocks_auto_claim_but_handoff_and_human_paths_continue(client, headers, app):
    require_postgres(app)
    auto = submit(client, headers).json()["ticket_id"]
    human = submit(client, headers, key="human-while-paused").json()["ticket_id"]
    grant(app, "admin", "AUTOMATION_STOP")
    assert stop(client, login_as(client, "admin")).status_code == 200
    assert action(client, headers, human, "request-agent").status_code == 201
    with app.state.session_factory.begin() as s:
        assert claim_jobs(s, "paused-auto") == []
        handoff = claim_jobs(s, "human-dispatch", job_kind="HANDOFF")
        assert len(handoff) == 1 and handoff[0]["ticket_id"] == human
        assert (
            s.scalar(select(automation_jobs.c.status).where(automation_jobs.c.ticket_id == auto)) == "PENDING"
        )
    assert client.get("/api/v1/tickets/" + auto, headers=headers).status_code == 200
    assert submit(client, headers, key="accepted-during-pause").status_code == 201


@pytest.mark.postgres
def test_resume_reclaims_stale_generation_with_new_token_without_activating_rules(client, headers, app):
    require_postgres(app)
    tid = submit(client, headers).json()["ticket_id"]
    old = lease_reply(app, tid)
    grant(app, "admin", "AUTOMATION_STOP", "AUTOMATION_RESUME")
    h = login_as(client, "admin")
    assert stop(client, h).status_code == 200 and resume(client, h).status_code == 200
    with app.state.session_factory.begin() as s:
        fresh = claim_jobs(s, "fresh-generation")[0]
        assert fresh["lease_token"] != str(old.lease_token) and fresh["automation_generation"] == 3
        assert (
            s.scalar(select(func.count()).select_from(automation_rules).where(automation_rules.c.active)) == 0
        )
    with pytest.raises(WorkRejected, match="INVALID_LEASE"), app.state.session_factory.begin() as s:
        commit_automatic_reply(s, old)
    from app.finalization import AutomaticReply

    with app.state.session_factory.begin() as s:
        commit_automatic_reply(
            s,
            AutomaticReply(
                job_id=fresh["job_id"],
                cycle_no=fresh["cycle_no"],
                expected_revision=fresh["expected_ticket_version"],
                worker_id="fresh-generation",
                lease_token=fresh["lease_token"],
                automation_generation=3,
                message="로컬 고정 답변",
            ),
        )


@pytest.mark.postgres
@pytest.mark.parametrize("first_operation", ["stop", "commit"])
def test_stop_and_final_commit_both_lock_orders(client, headers, app, first_operation):
    require_postgres(app)
    tid = submit(client, headers).json()["ticket_id"]
    reply = lease_reply(app, tid)
    grant(app, "admin", "AUTOMATION_STOP")
    held, release, q = Event(), Event(), Queue()

    def run(op, hold=False):
        try:
            with app.state.session_factory.begin() as s:
                pid = s.scalar(text("SELECT pg_backend_pid()"))
                if not hold:
                    q.put(pid)
                if op == "stop":
                    change(
                        s,
                        repository.get_user(s, stable_id("admin")),
                        StopCommand(expected_revision=1, reason_code="SAFETY_INCIDENT"),
                    )
                else:
                    commit_automatic_reply(s, reply)
                if hold:
                    held.set()
                    assert release.wait(10)
            return "OK"
        except WorkRejected as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, first_operation, True)
        try:
            assert held.wait(5)
            second = pool.submit(run, "commit" if first_operation == "stop" else "stop")
            wait_for_blocker(app, q.get(timeout=5))
        finally:
            release.set()
        assert first.result(timeout=10) == "OK"
        assert second.result(timeout=10) == ("AUTOMATION_PAUSED" if first_operation == "stop" else "OK")
    with app.state.session_factory() as s:
        assert s.scalar(select(automation_control.c.paused)) is True
        assert s.scalar(
            select(func.count())
            .select_from(messages)
            .where(messages.c.ticket_id == tid, messages.c.final_reply)
        ) == (0 if first_operation == "stop" else 1)


@pytest.mark.postgres
def test_concurrent_stop_revision_conflict_and_history_immutable(client, app):
    require_postgres(app)
    grant(app, "admin", "AUTOMATION_STOP")

    def change_once():
        try:
            with app.state.session_factory.begin() as s:
                change(
                    s,
                    repository.get_user(s, stable_id("admin")),
                    StopCommand(expected_revision=1, reason_code="OPERATOR_PAUSE"),
                )
            return "OK"
        except APIError as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: change_once(), range(2))) == ["AUTOMATION_REVISION_CONFLICT", "OK"]
    with pytest.raises(DBAPIError), app.state.session_factory.begin() as s:
        s.execute(automation_control_history.update().values(paused=False))


@pytest.mark.postgres
def test_missing_control_blocks_claim_without_mutating_job(client, headers, app):
    require_postgres(app)
    tid = submit(client, headers).json()["ticket_id"]
    with app.state.session_factory.begin() as s:
        s.execute(automation_control.delete())
    with (
        pytest.raises(WorkRejected, match="AUTOMATION_CONTROL_UNAVAILABLE"),
        app.state.session_factory.begin() as s,
    ):
        claim_jobs(s, "no-state")
    with app.state.session_factory() as s:
        row = s.execute(select(automation_jobs).where(automation_jobs.c.ticket_id == tid)).mappings().one()
        assert row["status"] == "PENDING" and row["lease_token"] is None


@pytest.mark.postgres
def test_control_query_failure_is_fail_closed(client, headers, app):
    require_postgres(app)
    tid = submit(client, headers).json()["ticket_id"]
    with app.state.engine.begin() as c:
        c.execute(text("ALTER TABLE automation_control RENAME TO unavailable_control"))
    try:
        with pytest.raises(SQLAlchemyError), app.state.session_factory.begin() as s:
            claim_jobs(s, "control-query-failed")
        with app.state.session_factory() as s:
            assert (
                s.scalar(select(automation_jobs.c.status).where(automation_jobs.c.ticket_id == tid))
                == "PENDING"
            )
        assert action(client, headers, tid, "request-agent").status_code == 201
        with app.state.session_factory.begin() as s:
            human = claim_jobs(s, "control-query-failed-human", job_kind="HANDOFF")
            assert len(human) == 1 and human[0]["ticket_id"] == tid
    finally:
        with app.state.engine.begin() as c:
            c.execute(text("ALTER TABLE unavailable_control RENAME TO automation_control"))


def test_control_history_survives_engine_restart_and_downgrade_is_refused(client, app):
    grant(app, "admin", "AUTOMATION_READ", "AUTOMATION_STOP")
    h = login_as(client, "admin")
    assert stop(client, h).status_code == 200
    app.state.engine.dispose()
    assert client.get(BASE + "/automation-control", headers=h).json()["paused"] is True
    with pytest.raises(RuntimeError, match="lose staff/control history"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0004")
    assert client.get("/health/ready").status_code == 200


def test_phase4_upgrade_preserves_fixture_and_creates_no_permissions(settings, monkeypatch, fixture_dir):
    migrate(settings, monkeypatch, "0004")
    engine = build_engine(settings)
    with session_factory(engine).begin() as s:
        seed_fixture(s, fixture_dir)
        count = s.scalar(select(func.count()).select_from(automation_jobs))
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    command.check(Config(str(ROOT / "alembic.ini")))
    with session_factory(engine).begin() as s:
        assert s.scalar(select(func.count()).select_from(automation_jobs)) == count
        assert s.scalar(select(func.count()).select_from(staff_permissions)) == 0
        assert s.scalar(select(automation_control.c.paused)) is False
        assert sum(seed_fixture(s, fixture_dir)["inserted"].values()) == 0
    command.downgrade(Config(str(ROOT / "alembic.ini")), "0004")
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine.dispose()
