import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db import build_engine, session_factory, utcnow
from app.models import tickets
from app.seed import seed_minimal, stable_id
from app.staff_models import staff_permissions
from tests.conftest import PASSWORD, ROOT, migrate
from tests.test_recommendations import URL, admin


@pytest.mark.postgres
def test_additive_permission_migration_preserves_rows_and_tables(settings, monkeypatch):
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL required")
    migrate(settings, monkeypatch, target="0009")
    e = build_engine(settings)
    try:
        f = session_factory(e)
        with f.begin() as s:
            seed_minimal(s, PASSWORD)
            s.execute(
                staff_permissions.insert().values(
                    user_id=stable_id("admin"), permission="QUALITY_METRICS_READ"
                )
            )
            s.execute(
                tickets.insert().values(
                    ticket_id=stable_id("recommend-migration-ticket"),
                    customer_id=stable_id("customer1/profile"),
                    sla_due_at=utcnow(),
                )
            )
            before = list(s.execute(select(tickets)))
            grants = list(s.execute(select(staff_permissions)))
            with pytest.raises(IntegrityError), s.begin_nested():
                s.execute(
                    staff_permissions.insert().values(
                        user_id=stable_id("admin"), permission="ASSIGNMENT_RECOMMEND"
                    )
                )
        tables = sorted(inspect(e).get_table_names())
        cfg = Config(str(ROOT / "alembic.ini"))
        command.upgrade(cfg, "0010")
        with f.begin() as s:
            assert s.scalar(text("SELECT version_num FROM alembic_version")) == "0010"
            assert before == list(s.execute(select(tickets))) and grants == list(
                s.execute(select(staff_permissions))
            )
        assert tables == sorted(inspect(e).get_table_names())
        command.downgrade(cfg, "0009")
        command.upgrade(cfg, "head")
        command.check(cfg)
    finally:
        e.dispose()


@pytest.mark.parametrize("history", [False, True])
def test_downgrade_refuses_permission_or_read_history(client, app, history):
    h = admin(client, app)
    if history:
        assert client.get(URL, headers=h).status_code == 200
        with app.state.session_factory.begin() as s:
            s.execute(
                staff_permissions.delete().where(staff_permissions.c.permission == "ASSIGNMENT_RECOMMEND")
            )
    with pytest.raises(RuntimeError, match="retain 0010"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0009")
    assert client.get("/health/ready").status_code == 200


def test_readiness_requires_0011(client, app):
    assert client.get("/health/ready").status_code == 200
    with app.state.session_factory.begin() as s:
        s.execute(text("UPDATE alembic_version SET version_num='0009'"))
    assert client.get("/health/ready").status_code == 503
