from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db import build_engine, session_factory, utcnow
from app.extensions.p1.models import p1_ai_call_attempts, p1_idempotency, p1_tasks
from app.main import create_app
from app.schema import metadata
from app.seed import seed_minimal, stable_id
from app.staff_models import staff_permissions
from tests.analytics_helpers import publish
from tests.conftest import PASSWORD, ROOT, login_as, migrate
from tests.phase6_helpers import material_fixture
from tests.test_flow import submit


def task(**overrides):
    now = utcnow()
    return (
        dict(
            task_id=str(uuid4()),
            kind="VOC_GENERATION",
            voc_request_id=str(uuid4()),
            requested_by=stable_id("admin"),
            context_key="a" * 64,
            status="QUEUED",
            created_at=now,
            updated_at=now,
            next_attempt_at=now,
        )
        | overrides
    )


@pytest.mark.parametrize("workload_granted", [False, True])
def test_0007_to_head_preserves_p0_and_no_grants(settings, monkeypatch, workload_granted):
    migrate(settings, monkeypatch, "0007")
    engine = build_engine(settings)
    with session_factory(engine).begin() as s:
        seed_minimal(s, PASSWORD)
        if workload_granted:
            s.execute(
                staff_permissions.insert().values(user_id=stable_id("admin"), permission="WORKLOAD_READ")
            )
    legacy_app = create_app(settings)
    with TestClient(legacy_app) as client:
        tid = submit(client, login_as(client, "customer1"), order=stable_id("customer1/order/0")).json()[
            "ticket_id"
        ]
        material_fixture(legacy_app.state.session_factory, tid, synthetic=False)
        publish(client, legacy_app)
    p0_tables = [t for t in metadata.sorted_tables if not t.name.startswith("p1_")]
    with session_factory(engine)() as s:
        before = {
            t.name: [dict(r) for r in s.execute(select(t).order_by(*t.primary_key.columns)).mappings()]
            for t in p0_tables
        }
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    command.check(Config(str(ROOT / "alembic.ini")))
    with session_factory(engine)() as s:
        for table in p0_tables:
            assert [
                dict(r) for r in s.execute(select(table).order_by(*table.primary_key.columns)).mappings()
            ] == before[table.name]
        assert s.scalar(select(func.count()).select_from(staff_permissions)) == int(workload_granted)
    assert {"p1_tasks", "p1_idempotency", "p1_ai_call_attempts"} <= set(inspect(engine).get_table_names())
    # Empty P1 storage can return to 0007, then forward again.
    command.downgrade(Config(str(ROOT / "alembic.ini")), "0007")
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine.dispose()


def test_task_constraints_and_partial_unique(app):
    first = task()
    with app.state.session_factory.begin() as s:
        s.execute(p1_tasks.insert().values(**first))
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as s:
        s.execute(p1_tasks.insert().values(**task()))
    for invalid in (
        task(context_key="b" * 64, status="RUNNING"),
        task(context_key="b" * 64, attempt=4),
        task(context_key="b" * 64, voc_request_id=None),
        task(context_key="b" * 64, status="SUCCEEDED"),
    ):
        with pytest.raises(IntegrityError), app.state.session_factory.begin() as s:
            s.execute(p1_tasks.insert().values(**invalid))
    with app.state.session_factory.begin() as s:
        s.execute(
            p1_tasks.update()
            .where(p1_tasks.c.task_id == first["task_id"])
            .values(status="SUCCEEDED", completed_at=utcnow())
        )
        s.execute(p1_tasks.insert().values(**task()))  # terminal task no longer blocks context


def test_attempt_target_fk_and_unknown_are_not_zero_tokens(app):
    t = task()
    with app.state.session_factory.begin() as s:
        s.execute(p1_tasks.insert().values(**t))
    values = dict(
        call_id=str(uuid4()),
        task_id=t["task_id"],
        component="P1_VOC",
        source="MOCK",
        attempt_no=1,
        outcome="UNKNOWN",
        started_at=utcnow(),
        finished_at=utcnow(),
    )
    with app.state.session_factory.begin() as s:
        s.execute(p1_ai_call_attempts.insert().values(**values))
        assert s.scalar(select(p1_ai_call_attempts.c.input_tokens)) is None
    for update in (
        {"call_id": str(uuid4())},
        {"call_id": str(uuid4()), "attempt_no": 2, "component": "BACKEND_B"},
        {"call_id": str(uuid4()), "attempt_no": 2, "task_id": str(uuid4())},
    ):
        with pytest.raises(IntegrityError), app.state.session_factory.begin() as s:
            s.execute(p1_ai_call_attempts.insert().values(**(values | update)))


@pytest.mark.parametrize("record", ["task", "permission", "idempotency"])
def test_downgrade_refuses_data_or_permission_loss(app, record):
    with app.state.session_factory.begin() as s:
        if record == "task":
            s.execute(p1_tasks.insert().values(**task()))
        elif record == "permission":
            s.execute(
                staff_permissions.insert().values(user_id=stable_id("admin"), permission="P1_MONITOR_READ")
            )
        else:
            s.execute(
                p1_idempotency.insert().values(
                    user_id=stable_id("admin"),
                    operation="VOC_GENERATE",
                    key="p1-record-0001",
                    request_hash="a" * 64,
                    response_status=202,
                    response_snapshot={},
                    created_at=utcnow(),
                )
            )
    with pytest.raises(RuntimeError, match="lose P1"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0007")
    with app.state.engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0008"
