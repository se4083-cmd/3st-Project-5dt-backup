import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select

from app import seed
from app.config import get_settings
from app.models import analytics_batches, automation_jobs, messages, tickets, users
from app.schema import metadata
from tests.conftest import ROOT, migrate


def test_initial_migration_and_reapplication(settings, monkeypatch):
    from app.db import build_engine

    migrate(settings, monkeypatch)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine = build_engine(settings)
    assert set(metadata.tables) <= set(inspect(engine).get_table_names())
    # Compare real migrated schema against model metadata, not just create_all.
    command.check(Config(str(ROOT / "alembic.ini")))
    command.downgrade(Config(str(ROOT / "alembic.ini")), "base")
    assert "tickets" not in inspect(engine).get_table_names()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine.dispose()
    get_settings.cache_clear()


def test_minimal_seed_idempotent_preserves_existing_password_and_user_data(app):
    with app.state.session_factory.begin() as session:
        before = session.scalar(select(func.count()).select_from(users))
        stored = session.scalar(
            select(users.c.password_hash).where(users.c.user_id == seed.stable_id("customer1"))
        )
        session.execute(
            users.update().where(users.c.user_id == seed.stable_id("customer1")).values(active=False)
        )
        seed.seed_minimal(session, "REVIEW_PW_3a6c609ff141698")
        assert session.scalar(select(func.count()).select_from(users)) == before
        assert (
            session.scalar(
                select(users.c.password_hash).where(users.c.user_id == seed.stable_id("customer1"))
            )
            == stored
        )
        assert (
            session.scalar(select(users.c.active).where(users.c.user_id == seed.stable_id("customer1")))
            is False
        )


def test_full_fixture_import_and_repeat_preserve_history(app, fixture_dir):
    with app.state.session_factory.begin() as session:
        first = seed.seed_fixture(session, fixture_dir)
        assert first["inserted"]["tickets"] == 1000
        assert first["inserted"]["messages"] == 4000
        assert first["source_as_of"] == "2026-10-31T03:00:00Z"
    with app.state.session_factory.begin() as session:
        old_ticket = session.scalar(select(tickets.c.ticket_id))
        session.execute(
            tickets.update().where(tickets.c.ticket_id == old_ticket).values(last_error_code="PRESERVE")
        )
        again = seed.seed_fixture(session, fixture_dir)
        assert sum(again["inserted"].values()) == 0
        assert (
            session.scalar(select(tickets.c.last_error_code).where(tickets.c.ticket_id == old_ticket))
            == "PRESERVE"
        )
        assert session.scalar(select(func.count()).select_from(tickets)) == 1000
        assert session.scalar(select(func.count()).select_from(messages)) == 4000
        assert session.scalar(select(func.count()).select_from(automation_jobs)) == 1000
        batch = session.execute(select(analytics_batches)).mappings().one()
        assert batch["status"] == "VALIDATED" and batch["is_current"] is False
        disabled = session.scalar(
            select(users.c.password_hash).where(users.c.login_name == "customer0000@example.test")
        )
        assert disabled == "!DISABLED_SYNTHETIC_LOGIN"


def test_fixture_failure_rolls_back_all_tables(app, fixture_dir, monkeypatch):
    original = seed.insert_missing

    def fail_on_messages(session, table, rows):
        if table.name == "messages":
            raise ValueError("deliberate late import failure after approval inserts")
        return original(session, table, rows)

    monkeypatch.setattr(seed, "insert_missing", fail_on_messages)
    with pytest.raises(ValueError), app.state.session_factory.begin() as session:
        seed.seed_fixture(session, fixture_dir)
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(tickets)) == 0
        assert session.scalar(select(func.count()).select_from(analytics_batches)) == 0
        assert session.scalar(select(func.count()).select_from(users)) == 4


def test_new_ticket_after_full_fixture_import(client, headers, app, fixture_dir):
    from tests.test_flow import submit

    with app.state.session_factory.begin() as session:
        seed.seed_fixture(session, fixture_dir)
    assert submit(client, headers).status_code == 201
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(tickets)) == 1001
