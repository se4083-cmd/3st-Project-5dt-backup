"""Real PG repeatable-read and additive capability migration verification."""

from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app import audit, workload
from app.db import utcnow
from app.model_constraints import user_team_scopes
from app.models import assignments, audit_events, tickets
from app.seed import stable_id
from app.staff_models import staff_permissions
from tests.conftest import ROOT, migrate
from tests.test_finalization_contract import require_postgres
from tests.test_workload import URL, admin, followup, get, ticket


@pytest.mark.postgres
def test_snapshot_auth_counts_and_followups_do_not_mix_committed_changes(client, app, monkeypatch):
    require_postgres(app)
    h = admin(client, app)
    tid = ticket(app)
    followup(app, tid)
    with app.state.session_factory.begin() as s:
        s.execute(
            assignments.update()
            .where(assignments.c.ticket_id == tid)
            .values(assigned_at=utcnow() - timedelta(hours=1))
        )
    original = workload.ticket_counts
    called = False

    def switch_after_ticket_counts(session, *args, **kwargs):
        nonlocal called
        counts = original(session, *args, **kwargs)
        assert session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        if not called:
            called = True
            # A separate committed transaction changes assignment + followup
            # eligibility after the request established its authenticated snapshot.
            with app.state.session_factory.begin() as writer:
                writer.execute(
                    assignments.update().where(assignments.c.ticket_id == tid).values(ended_at=utcnow())
                )
                writer.execute(
                    user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin"))
                )
        return counts

    monkeypatch.setattr(workload, "ticket_counts", switch_after_ticket_counts)
    result = get(client, h)
    assert called
    assert result["scope_totals"]["tickets"]["total"] == 1
    assert result["scope_totals"]["followups"]["total"] == 1
    assert result["team_queue"]["waiting_followups"]["total"] == 0
    assert result["scope_totals"] == result["page_totals"]
    # Next request sees the scope revocation: no cached counts or identities.
    result = get(client, h)
    assert result["team_ids"] == [] and result["items"] == []
    assert result["scope_totals"]["tickets"]["total"] == 0


@pytest.mark.postgres
def test_migration_preserves_business_rows_grants_nothing_and_matches_models(settings, monkeypatch):
    from app.db import build_engine, session_factory
    from app.seed import seed_minimal
    from tests.conftest import PASSWORD

    require = settings.database_url.startswith("postgresql")
    if not require:
        pytest.skip("Requires isolated PostgreSQL")
    migrate(settings, monkeypatch, target="0006")
    engine = build_engine(settings)
    factory = session_factory(engine)
    try:
        with factory.begin() as s:
            seed_minimal(s, PASSWORD)
            s.execute(
                tickets.insert().values(
                    ticket_id=str(uuid4()),
                    customer_id=stable_id("customer1/profile"),
                    sla_due_at=utcnow() + timedelta(days=1),
                )
            )
            before = [tuple(x) for x in s.execute(select(tickets))]
            grants = list(s.execute(select(staff_permissions)))
            with pytest.raises(IntegrityError), s.begin_nested():
                s.execute(
                    staff_permissions.insert().values(user_id=stable_id("admin"), permission="WORKLOAD_READ")
                )
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        with factory.begin() as s:
            assert s.scalar(text("SELECT version_num FROM alembic_version")) == "0008"
            assert before == [tuple(x) for x in s.execute(select(tickets))]
            assert grants == list(s.execute(select(staff_permissions)))
        command.check(Config(str(ROOT / "alembic.ini")))
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0006")
        command.upgrade(Config(str(ROOT / "alembic.ini")), "0007")
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        command.check(Config(str(ROOT / "alembic.ini")))
    finally:
        engine.dispose()


@pytest.mark.postgres
@pytest.mark.parametrize("history", [False, True])
def test_downgrade_refuses_authorization_or_read_history(app, settings, monkeypatch, history):
    require_postgres(app)
    migrate(settings, monkeypatch)
    with app.state.session_factory.begin() as s:
        if history:
            audit.record(s, stable_id("agent"), "READ_WORKLOAD", "WORKLOAD", None)
        else:
            s.execute(
                staff_permissions.insert().values(user_id=stable_id("admin"), permission="WORKLOAD_READ")
            )
    with pytest.raises(RuntimeError, match="retain 0007"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0006")
    with app.state.session_factory() as s:
        assert s.scalar(text("SELECT version_num FROM alembic_version")) == "0008"


def test_workload_audit_failure_returns_no_partial_response(client, app, monkeypatch):
    h = admin(client, app)
    original = audit.record

    def fail(session, actor, action, *args, **kwargs):
        if action == "READ_WORKLOAD":
            raise RuntimeError("synthetic audit failure")
        return original(session, actor, action, *args, **kwargs)

    monkeypatch.setattr(audit, "record", fail)
    r = client.get(URL, headers=h)
    assert r.status_code == 500 and set(r.json()) == {"error"}
    with app.state.session_factory() as s:
        assert (
            s.scalar(
                select(func.count()).select_from(audit_events).where(audit_events.c.action == "READ_WORKLOAD")
            )
            == 0
        )


def test_readiness_requires_workload_migration(client, app):
    assert client.get("/health/ready").status_code == 200
    with app.state.session_factory.begin() as s:
        s.execute(text("UPDATE alembic_version SET version_num='0006'"))
    assert client.get("/health/ready").status_code == 503
