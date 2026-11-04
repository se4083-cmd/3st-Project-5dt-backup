from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Column, MetaData, Table, Uuid, select, text
from sqlalchemy.exc import IntegrityError

from app import seed
from app.db import build_engine, session_factory, utcnow
from app.models import followup_actions, tickets
from tests.conftest import PASSWORD, ROOT, login_as, migrate
from tests.phase3_helpers import create_followup, make_ticket


@pytest.mark.parametrize(
    "values",
    [
        {"status": "DONE"},
        {"status": "CANCELLED"},
        {"completed_at": "now"},
        {"cycle_no": None},
        {"responsibility_cycle_no": 0},
        {"origin_team_id": None},
        {"due_at": "past"},
        {"version": 0},
    ],
)
def test_followup_database_lifecycle_checks(client, headers, app, values):
    tid = make_ticket(client, headers, app)
    aid = create_followup(client, login_as(client, "agent"), tid).json()["action_id"]
    if values.get("completed_at") == "now":
        values = {"completed_at": utcnow()}
    if values.get("due_at") == "past":
        values = {"due_at": utcnow() - timedelta(days=2)}
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(followup_actions.update().where(followup_actions.c.action_id == aid).values(**values))


def test_phase2_followup_upgrade_preserves_origin_and_legacy_fields(settings, monkeypatch):
    migrate(settings, monkeypatch, "0002")
    engine = build_engine(settings)
    now = utcnow()
    tid, aid = str(uuid4()), str(uuid4())
    with session_factory(engine).begin() as session:
        seed.seed_minimal(session, PASSWORD)
        session.execute(
            tickets.insert().values(
                ticket_id=tid, customer_id=seed.stable_id("customer1/profile"), sla_due_at=now
            )
        )
        # Reflect the pre-0003 shape: do not use new model defaults on an old schema.
        old = Table(
            "followup_actions",
            MetaData(),
            *(
                Column(name, Uuid(as_uuid=False), primary_key=(name == "action_id"))
                for name in ["action_id", "ticket_id", "product_id", "owner_user_id", "owner_team_id"]
            ),
            autoload_with=session.connection(),
        )
        session.execute(
            old.insert().values(
                action_id=aid,
                ticket_id=tid,
                product_id=None,
                cycle_no=1,
                owner_team_id=seed.stable_id("team"),
                owner_user_id=seed.stable_id("agent"),
                kind="CHECK",
                status="IN_PROGRESS",
                public_note="original public",
                internal_note="original private",
                blocks_resolution=True,
                due_at=now + timedelta(days=1),
                completed_at=None,
                version=2,
                created_at=now,
                updated_at=now,
                data_origin="SYNTHETIC",
                scenario_id="TEST",
                generator_version="TEST",
                seed=0,
            )
        )
        before = tuple(
            session.execute(
                text("SELECT status, version, public_note, internal_note FROM followup_actions")
            ).one()
        )
    migrate(settings, monkeypatch)
    with engine.connect() as connection:
        assert (
            tuple(
                connection.execute(
                    text("SELECT status, version, public_note, internal_note FROM followup_actions")
                ).one()
            )
            == before
        )
        row = connection.execute(select(followup_actions)).mappings().one()
        assert row["cycle_no"] == row["responsibility_cycle_no"] == 1
        assert row["origin_team_id"] == row["owner_team_id"]
        assert row["cancelled_at"] is None and row["cancellation_reason"] is None
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0009"
    engine.dispose()


def test_phase3_downgrade_refuses_history_loss(client, headers, app):
    tid = make_ticket(client, headers, app)
    assert create_followup(client, login_as(client, "agent"), tid).status_code == 201
    with pytest.raises(RuntimeError, match="lose followup history"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0002")
    assert client.get("/health/ready").status_code == 200
