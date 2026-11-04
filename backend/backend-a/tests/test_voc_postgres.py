"""Additive schema preservation and retention references on disposable local PG."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text

from app.db import build_engine, session_factory, utcnow
from app.models import followup_actions, tickets
from app.seed import seed_minimal, stable_id
from app.staff_models import staff_permissions
from app.voc_models import profiles
from tests.analytics_helpers import publish
from tests.conftest import PASSWORD, ROOT, migrate
from tests.phase3_helpers import make_ticket
from tests.test_voc_improvements import admin, create, link, plan


@pytest.mark.postgres
def test_migration_preserves_old_data_and_grants_and_matches_metadata(settings, monkeypatch):
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Real PG required")
    migrate(settings, monkeypatch, target="0007")
    engine = build_engine(settings)
    factory = session_factory(engine)
    try:
        with factory.begin() as s:
            seed_minimal(s, PASSWORD)
            s.execute(
                staff_permissions.insert().values(user_id=stable_id("admin"), permission="WORKLOAD_READ")
            )
            before = [tuple(x) for x in s.execute(select(staff_permissions))]
            s.execute(
                followup_actions.insert().values(
                    action_id=str(uuid4()),
                    product_id=stable_id("product"),
                    owner_team_id=stable_id("team"),
                    owner_user_id=stable_id("admin"),
                    kind="EXISTING_GENERAL_PRODUCT",
                    status="OPEN",
                    version=3,
                    blocks_resolution=False,
                    internal_note="synthetic preserved note",
                )
            )
            business = [tuple(x) for x in s.execute(select(followup_actions))]
        cfg = Config(str(ROOT / "alembic.ini"))
        command.upgrade(cfg, "head")
        with factory.begin() as s:
            assert s.scalar(text("SELECT version_num FROM alembic_version")) == "0008"
            assert before == [tuple(x) for x in s.execute(select(staff_permissions))]
            assert business == [tuple(x) for x in s.execute(select(followup_actions))]
            assert s.scalar(select(func.count()).select_from(profiles)) == 0
        command.check(cfg)
        command.downgrade(cfg, "0007")
        command.upgrade(cfg, "0008")
        command.check(cfg)
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_profile_prevents_destructive_downgrade_and_readiness(client, app, monkeypatch):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("Real PG required")
    h = admin(client, app)
    create(client, h)
    with pytest.raises(RuntimeError, match="retain 0008"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0007")
    assert client.get("/health/ready").status_code == 200
    with app.state.session_factory.begin() as s:
        s.execute(text("UPDATE alembic_version SET version_num='0007'"))
    assert client.get("/health/ready").status_code == 503


def test_retention_source_link_and_global_product_followup_protection(client, headers, app, monkeypatch):
    from datetime import timedelta

    h = admin(client, app)
    batch, _ = publish(client, app)
    aid = create(client, h, plan=plan(source_batch_id=batch["manifest"]["batch_id"], source_scope_key="T1"))
    tid = make_ticket(client, headers, app)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(product_id=stable_id("product")))
    assert link(client, h, aid, tid).status_code == 201
    with app.state.session_factory.begin() as s:
        for cap in ("RETENTION_GLOBAL_REVIEW", "RETENTION_TEAM_REVIEW"):
            s.execute(staff_permissions.insert().values(user_id=stable_id("admin"), permission=cap))
    # Test-only clock: do not mutate published/immutable rows to make them old.
    from app import retention

    future = utcnow() + timedelta(days=200)
    original = retention.build_report

    def simulated_snapshot(session, user, body):
        session.info["snapshot_as_of"] = future
        return original(session, user, body)

    monkeypatch.setattr(retention, "build_report", simulated_snapshot)
    asof = future.isoformat()

    def review(scope):
        r = client.post(
            "/api/v1/staff/retention/dry-run",
            headers=h,
            json={"purpose_code": "RETENTION_REVIEW", "scope": scope, "as_of": asof},
        )
        assert r.status_code == 200, r.text
        return {v["target"]: v for v in r.json()["targets"]}

    global_ = review("GLOBAL")
    assert global_["tickets"]["reason_counts"]["VOC_IMPROVEMENT_TICKET_REFERENCE"] == 1
    assert global_["analytics_batches"]["reason_counts"]["VOC_PLAN_SOURCE_BATCH_REFERENCE"] == 1
    assert (
        global_["followup_actions:without_ticket"]["reason_counts"]["VOC_IMPROVEMENT_PROFILE_REFERENCE"] == 1
    )
    for t in [
        "voc_improvement_profiles",
        "voc_improvement_plan_revisions",
        "voc_improvement_ticket_links",
        "voc_improvement_receipts",
    ]:
        assert global_[t]["candidate_count"] == 0 and global_[t]["blocked_count"] >= 1
    team = review("TEAM")
    assert team["voc_improvement_plan_revisions"]["inspection"] == "UNSUPPORTED_TEAM_SCOPE"
    assert team["voc_improvement_plan_revisions"]["inspected_count"] is None
