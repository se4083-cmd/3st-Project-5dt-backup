from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text

from app.db import build_engine, session_factory, utcnow
from app.effect_models import effect_batches
from app.models import tickets
from app.monitor_models import cycles, monitor_epoch
from app.seed import seed_minimal, stable_id
from app.staff_models import staff_permissions
from tests.conftest import PASSWORD, ROOT, login_as, migrate


def test_0011_upgrade_preserves_existing_rows_and_no_history_backfill(settings, monkeypatch):
    migrate(settings, monkeypatch, target="0010")
    e = build_engine(settings)
    f = session_factory(e)
    try:
        with f.begin() as s:
            seed_minimal(s, PASSWORD)
            s.execute(
                tickets.insert().values(
                    ticket_id=stable_id("monitor-old"),
                    customer_id=stable_id("customer1/profile"),
                    sla_due_at=utcnow(),
                )
            )
            s.execute(
                staff_permissions.insert().values(user_id=stable_id("admin"), permission="WORKLOAD_READ")
            )
            before = list(s.execute(select(tickets)))
            grants = list(s.execute(select(staff_permissions)))
        cfg = Config(str(ROOT / "alembic.ini"))
        command.upgrade(cfg, "head")
        with f.begin() as s:
            assert s.scalar(text("SELECT version_num FROM alembic_version")) == "0011"
            assert (
                list(s.execute(select(tickets))) == before
                and list(s.execute(select(staff_permissions))) == grants
            )
            assert s.scalar(select(func.count()).select_from(cycles)) == 0
            assert s.scalar(select(func.count()).select_from(effect_batches)) == 0
            assert s.scalar(select(func.count()).select_from(monitor_epoch)) == 1
        command.check(cfg)
        command.downgrade(cfg, "0010")
        command.upgrade(cfg, "head")
        command.check(cfg)
    finally:
        e.dispose()


def test_cycle_failure_rolls_back_ticket_message_job_receipt(client, app, monkeypatch):
    from app import automation_monitor

    def fail(*a, **kw):
        raise RuntimeError("synthetic monitor failure")

    monkeypatch.setattr(automation_monitor, "start_cycle", fail)
    h = login_as(client, "customer1")
    r = client.post(
        "/api/v1/tickets",
        headers={**h, "Idempotency-Key": "monitor-atomic-001"},
        json={"message": "합성 테스트"},
    )
    assert r.status_code == 500
    from app.model_constraints import idempotency_keys
    from app.models import automation_jobs, messages

    with app.state.session_factory() as s:
        for t in [tickets, automation_jobs, messages, idempotency_keys, cycles]:
            assert s.scalar(select(func.count()).select_from(t)) == 0


def test_monitor_retention_history_protected_and_readiness(client, app):
    from datetime import timedelta

    from app.automation_monitor import start_cycle
    from app.models import automation_jobs
    from tests.quality_helpers import command

    c = command(app)
    with app.state.session_factory.begin() as s:
        tid = s.scalar(select(automation_jobs.c.ticket_id).where(automation_jobs.c.job_id == str(c.job_id)))
        # Synthetic time-shifted observation, not a legacy backfill operation.
        start_cycle(s, tid, 1, "AUTO", 1, utcnow() - timedelta(days=35), origin="SYNTHETIC")
    from tests.quality_helpers import grant

    grant(app, "admin", "RETENTION_GLOBAL_REVIEW")
    r = client.post(
        "/api/v1/staff/retention/dry-run",
        headers=login_as(client, "admin"),
        json={"scope": "GLOBAL", "purpose_code": "RETENTION_REVIEW", "as_of": utcnow().isoformat()},
    )
    assert r.status_code == 200, r.text
    value = r.json()
    assert "automation_cycle_records" in str(value) and "voc_effect_batches" in str(value)
    assert "PROSPECTIVE_MONITOR_EFFECT_HISTORY_REFERENCE" in str(value)
    with app.state.session_factory.begin() as s:
        s.execute(text("UPDATE alembic_version SET version_num='0010'"))
    assert client.get("/health/ready").status_code == 503
