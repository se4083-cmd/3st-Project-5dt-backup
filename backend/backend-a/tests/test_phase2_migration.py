import hashlib
import json
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import auth, seed
from app.db import build_engine, session_factory, utcnow
from app.main import create_app
from app.model_constraints import idempotency_keys
from app.models import automation_jobs, customers, messages, tickets
from tests.conftest import PASSWORD, ROOT, migrate
from tests.test_flow import submit
from tests.test_ticket_commands import action, load_ticket


def test_upgrade_preserves_phase1_data_and_idempotent_receipt(settings, monkeypatch):
    migrate(settings, monkeypatch, "0001")
    engine = build_engine(settings)
    ticket_id, job_id = str(uuid4()), str(uuid4())
    body = {"message": "phase-one request", "order_id": None}
    digest = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    now = utcnow()
    with session_factory(engine).begin() as session:
        seed.seed_minimal(session, PASSWORD)
        session.execute(
            tickets.insert().values(
                ticket_id=ticket_id,
                customer_id=seed.stable_id("customer1/profile"),
                sla_due_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            messages.insert().values(
                message_id=str(uuid4()),
                ticket_id=ticket_id,
                cycle_no=1,
                role="CUSTOMER",
                direction="IN",
                body=body["message"],
                visibility="PUBLIC",
            )
        )
        session.execute(
            automation_jobs.insert().values(
                job_id=job_id, ticket_id=ticket_id, cycle_no=1, expected_ticket_version=1
            )
        )
        session.execute(
            idempotency_keys.insert().values(
                user_id=seed.stable_id("customer1"),
                key="old-key-0001",
                request_hash=digest,
                ticket_id=ticket_id,
                created_at=now,
            )
        )
        before = [tuple(r) for r in session.execute(text("SELECT * FROM tickets"))]
    migrate(settings, monkeypatch)
    with engine.connect() as connection:
        assert [tuple(r) for r in connection.execute(text("SELECT * FROM tickets"))] == before
        assert connection.scalar(select(automation_jobs.c.job_kind)) == "AUTO"
        assert connection.scalar(select(idempotency_keys.c.operation)) == "CREATE_TICKET"
    app = create_app(settings)
    with TestClient(app) as client:
        from tests.conftest import login_as

        headers = login_as(client, "customer1")
        assert submit(client, headers, key="old-key-0001", message=body["message"]).status_code == 200
        assert action(client, headers, ticket_id).status_code == 201
    engine.dispose()


def test_downgrade_refuses_to_discard_phase2_commands(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    assert action(client, headers, ticket_id).status_code == 201
    with pytest.raises(RuntimeError, match="lose command history"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0001")
    assert load_ticket(app, ticket_id)["cycle_no"] == 2


def test_reopen_original_fixture_preserves_history_and_seed_reexecution(client, app, fixture_dir):
    with app.state.session_factory.begin() as session:
        seed.seed_fixture(session, fixture_dir)
        original = (
            session.execute(select(tickets).where(tickets.c.data_origin == "SYNTHETIC")).mappings().first()
        )
        user_id = session.scalar(
            select(customers.c.user_id).where(customers.c.customer_id == original["customer_id"])
        )
        old_messages = [
            dict(r)
            for r in session.execute(
                select(messages).where(messages.c.ticket_id == original["ticket_id"])
            ).mappings()
        ]
        old_job = dict(
            session.execute(
                select(automation_jobs).where(automation_jobs.c.ticket_id == original["ticket_id"])
            )
            .mappings()
            .one()
        )
    # Test-only issuer: fixture passwords remain disabled; no login credentials are enabled.
    headers = {"Authorization": "Bearer " + auth.issue_token(user_id, app.state.settings)}
    result = action(client, headers, original["ticket_id"], revision=original["version"])
    assert result.status_code == 201
    with app.state.session_factory.begin() as session:
        assert sum(seed.seed_fixture(session, fixture_dir)["inserted"].values()) == 0
        for message in old_messages:
            row = (
                session.execute(select(messages).where(messages.c.message_id == message["message_id"]))
                .mappings()
                .one()
            )
            assert dict(row) == message
        assert (
            dict(
                session.execute(select(automation_jobs).where(automation_jobs.c.job_id == old_job["job_id"]))
                .mappings()
                .one()
            )
            == old_job
        )
    assert load_ticket(app, original["ticket_id"])["cycle_no"] == 2
