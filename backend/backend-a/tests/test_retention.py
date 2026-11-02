from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from app import audit
from app import models as m
from app.db import build_engine, session_factory
from app.model_constraints import idempotency_keys
from app.seed import seed_fixture, stable_id
from app.staff_models import queue_routes
from tests.conftest import ROOT, login_as, migrate
from tests.phase3_helpers import staff_user
from tests.phase6_helpers import material_fixture
from tests.phase7_helpers import AS_OF, BODY, OLD, URL, archived, business_hashes, grant, target


@pytest.mark.parametrize("role", ["customer1", "agent", "admin"])
def test_retention_requires_explicit_capability(client, app, role):
    assert client.post(URL, headers=login_as(client, role), json=BODY).status_code == 403


@pytest.mark.parametrize("role", ["customer1", "agent"])
def test_retention_capability_does_not_bypass_admin_requirement(client, app, role):
    grant(app.state.session_factory, role)
    assert client.post(URL, headers=login_as(client, role), json=BODY).status_code == 403


def test_team_scope_unknown_custody_other_team_and_no_global_escalation(client, app):
    factory = app.state.session_factory
    other = stable_id("other-retention-team")
    staff_user(app, "retention-other-agent", team_id=other)
    archived(factory, cycle=1)
    archived(factory, team=None, cycle=1)
    archived(factory, team="other-retention-team", cycle=1)
    archived(factory, cycle=2)  # historical custody unknown, no guessed team
    grant(factory, permission="RETENTION_TEAM_REVIEW")
    h = login_as(client, "admin")
    assert client.post(URL, headers=h, json=BODY).status_code == 403
    r = client.post(URL, headers=h, json={**BODY, "scope": "TEAM"})
    assert r.status_code == 200
    report = r.json()
    assert target(report, "messages")["inspected_count"] == 1
    for name in ["analytics_receipts", "analytics_daily", "customers", "users"]:
        item = target(report, name)
        assert item["inspection"] == "UNSUPPORTED_TEAM_SCOPE" and item["inspected_count"] is None
        assert item["reason_counts"] == {}
    assert client.post(URL, headers=h, json={**BODY, "scope": "TEAM", "team_ids": [other]}).status_code == 403
    assert report["team_ids"] == [stable_id("team")]
    # Adding hidden material changes no visible team counts/fingerprint.
    archived(factory, team=None, cycle=1)
    archived(factory, team="other-retention-team", cycle=1)
    again = client.post(URL, headers=h, json={**BODY, "scope": "TEAM"}).json()
    assert again["result_fingerprint"] == report["result_fingerprint"]


def test_team_historical_route_and_cross_custody_are_conservative(client, app):
    f = app.state.session_factory
    tid, _ = archived(f)
    grant(f, permission="RETENTION_TEAM_REVIEW")
    h = login_as(client, "admin")
    body = {**BODY, "scope": "TEAM"}
    assert target(client.post(URL, headers=h, json=body).json(), "messages")["inspected_count"] == 0
    with f.begin() as s:
        for cycle in (1, 2):
            s.execute(
                queue_routes.insert().values(
                    ticket_id=tid,
                    cycle_no=cycle,
                    team_id=stable_id("team"),
                    revision=1,
                    recorded_by_service="local-test",
                )
            )
    assert target(client.post(URL, headers=h, json=body).json(), "messages")["inspected_count"] == 1
    with f.begin() as s:
        s.execute(
            queue_routes.update()
            .where(queue_routes.c.ticket_id == tid, queue_routes.c.cycle_no == 1)
            .values(team_id=None)
        )
    assert target(client.post(URL, headers=h, json=body).json(), "messages")["inspected_count"] == 0


@pytest.mark.parametrize("offset,expected", [(-1, 1), (0, 0), (1, 0)])
def test_exact_utc_microsecond_boundary(client, app, offset, expected):
    f = app.state.session_factory
    archived(f, at=AS_OF - timedelta(days=30) + timedelta(microseconds=offset))
    grant(f)
    r = client.post(URL, headers=login_as(client, "admin"), json=BODY)
    assert r.status_code == 200
    item = target(r.json(), "messages")
    assert item["past_retention_count"] == expected
    assert r.json()["as_of"] == "2026-10-31T03:00:00Z"


def test_policy_parameters_and_offset_normalization(client, app):
    f = app.state.session_factory
    archived(f, at=AS_OF - timedelta(days=40))
    grant(f)
    h = login_as(client, "admin")
    small = client.post(URL, headers=h, json=BODY).json()
    large = client.post(
        URL,
        headers=h,
        json={
            **BODY,
            "as_of": "2026-10-31T12:00:00+09:00",
            "policy": {"raw_days": 60, "aggregate_days": 180},
        },
    ).json()
    assert target(small, "messages")["past_retention_count"] == 1
    assert target(large, "messages")["past_retention_count"] == 0
    assert small["policy_hash"] != large["policy_hash"] and small["as_of"] == large["as_of"]
    assert small["candidate_ids_available"] is False
    assert all(x["candidate_count"] in (0, None) for x in small["targets"])


def test_recent_ticket_activity_restarts_raw_clock_and_preserves_old_cycle(client, app):
    f = app.state.session_factory
    tid, _ = archived(f)
    with f.begin() as s:
        s.execute(
            m.tickets.update()
            .where(m.tickets.c.ticket_id == tid)
            .values(updated_at=AS_OF - timedelta(days=1))
        )
    grant(f)
    r = client.post(URL, headers=login_as(client, "admin"), json=BODY)
    assert r.status_code == 200
    assert target(r.json(), "messages")["inspected_count"] == 1
    assert target(r.json(), "messages")["past_retention_count"] == 0


def test_approval_policy_and_json_snapshot_reference_inventory(client, app):
    f = app.state.session_factory
    tid, _ = archived(f)
    with f.begin() as s:
        product = s.scalar(
            select(m.orders.c.product_id).where(m.orders.c.order_id == stable_id("customer1/order/0"))
        )
        s.execute(
            m.tickets.update()
            .where(m.tickets.c.ticket_id == tid)
            .values(order_id=stable_id("customer1/order/0"), product_id=product)
        )
    material_fixture(f, tid)
    with f.begin() as s:
        for table in [m.ai_suggestions, m.approvals]:
            s.execute(
                table.update()
                .where(table.c.ticket_id == tid)
                .values(cycle_no=1, created_at=OLD, updated_at=OLD)
            )
    grant(f)
    report = client.post(URL, headers=login_as(client, "admin"), json=BODY).json()
    assert target(report, "messages")["reason_counts"]["APPROVAL_REFERENCE"] == 1
    ai = target(report, "ai_suggestions")
    assert ai["reason_counts"]["SUGGESTION_APPROVAL_REFERENCE"] == 1
    assert ai["past_retention_count"] == 1 and ai["candidate_count"] == 0
    assert {"draft", "order_snapshot", "evidence_refs", "gate_results"} <= set(ai["fields"])
    assert target(report, "knowledge_documents")["undetermined_count"] == 1


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("unresolved", "UNRESOLVED_TICKET"),
        ("current", "CURRENT_OR_FUTURE_CYCLE"),
        ("followup", "MANDATORY_FOLLOWUP_OPEN_ANY_CYCLE"),
        ("assignment", "ACTIVE_ASSIGNMENT_ANY_CYCLE"),
        ("job", "ACTIVE_JOB_OR_VALID_LEASE"),
        ("lease", "ACTIVE_JOB_OR_VALID_LEASE"),
        ("idempotency", "IDEMPOTENCY_RETRY_REFERENCE"),
        ("audit", "AUDIT_REFERENCE"),
    ],
)
def test_business_protection_all_cycles(client, app, kind, reason):
    f = app.state.session_factory
    tid, mid = archived(f)
    with f.begin() as s:
        if kind == "unresolved":
            s.execute(
                m.tickets.update()
                .where(m.tickets.c.ticket_id == tid)
                .values(status="PROCESSING", resolved_at=None, resolution_mode=None)
            )
        elif kind == "current":
            s.execute(m.messages.update().where(m.messages.c.message_id == mid).values(cycle_no=2))
        elif kind == "followup":
            s.execute(
                m.followup_actions.insert().values(
                    action_id=str(uuid4()),
                    ticket_id=tid,
                    cycle_no=1,
                    responsibility_cycle_no=1,
                    status="OPEN",
                    kind="INTERNAL_CHECK",
                    version=1,
                    blocks_resolution=True,
                    owner_team_id=stable_id("team"),
                    origin_team_id=stable_id("team"),
                    public_note="PRIVATE_RETENTION_FOLLOWUP",
                    internal_note="PRIVATE_RETENTION_INTERNAL",
                    created_at=OLD,
                    updated_at=OLD,
                )
            )
        elif kind == "assignment":
            s.execute(
                m.assignments.insert().values(
                    assignment_id=str(uuid4()),
                    ticket_id=tid,
                    cycle_no=1,
                    team_id=stable_id("team"),
                    agent_id=stable_id("agent"),
                    assigned_at=OLD,
                    reason_code="TEST_ONLY",
                )
            )
        elif kind in {"job", "lease"}:
            s.execute(
                m.automation_jobs.insert().values(
                    job_id=str(uuid4()),
                    ticket_id=tid,
                    cycle_no=1,
                    status="PENDING" if kind == "job" else "RUNNING",
                    expected_ticket_version=1,
                    lease_until=AS_OF + timedelta(days=1) if kind == "lease" else None,
                    lease_token=str(uuid4()) if kind == "lease" else None,
                    lease_owner="local-retention-test" if kind == "lease" else None,
                    next_attempt_at=OLD,
                )
            )
        elif kind == "idempotency":
            s.execute(
                idempotency_keys.insert().values(
                    user_id=stable_id("customer1"),
                    key="retention-retry",
                    request_hash="0" * 64,
                    ticket_id=tid,
                    response_snapshot={"note": "PRIVATE_RETENTION_RETRY"},
                    created_at=OLD,
                )
            )
        elif kind == "audit":
            audit.record(s, stable_id("admin"), "TEST_REFERENCE", "TICKET", tid, ticket=tid, cycle=1)
    grant(f)
    r = client.post(URL, headers=login_as(client, "admin"), json=BODY).json()
    row = target(r, "messages")
    assert row["reason_counts"][reason] == 1 and row["blocked_count"] == 1 and row["candidate_count"] == 0


@pytest.mark.parametrize(
    "invalid",
    [
        {"as_of": "2026-10-31T03:00:00"},
        {"as_of": "2099-01-01T00:00:00Z"},
        {"policy": {"raw_days": 0}},
        {"policy": {"aggregate_days": 3651}},
        {"policy": {"raw_days": True}},
        {"policy": {"version": "production-certified"}},
        {"table": "messages; DROP TABLE tickets"},
        {"sql": "SELECT body FROM messages"},
        {"path": "C:/private/.env"},
        {"url": "https://external.invalid"},
        {"execute": True},
        {"force": True},
        {"team_ids": [stable_id("team")]},
        {"scope": "TEAM", "team_ids": [stable_id("team"), stable_id("team")]},
        {"purpose_code": "PRIVATE_RETENTION_PURPOSE"},
    ],
)
def test_invalid_or_executable_inputs_rejected(client, app, invalid):
    grant(app.state.session_factory)
    r = client.post(URL, headers=login_as(client, "admin"), json={**BODY, **invalid})
    assert r.status_code == 422 and "PRIVATE_RETENTION" not in r.text and "DROP" not in r.text


def test_preview_changes_only_minimal_audit_and_never_returns_values(client, app, caplog):
    f = app.state.session_factory
    archived(f)
    grant(f)
    h = login_as(client, "admin")
    before = business_hashes(f)
    with f() as s:
        n = s.scalar(select(func.count()).select_from(m.audit_events))
    r = client.post(URL, headers=h, json=BODY)
    assert r.status_code == 200
    assert "PRIVATE_RETENTION" not in r.text and "PRIVATE_RETENTION" not in caplog.text
    assert before == business_hashes(f)
    with f() as s:
        assert s.scalar(select(func.count()).select_from(m.audit_events)) == n + 1
        row = (
            s.execute(select(m.audit_events).where(m.audit_events.c.action == "RETENTION_DRY_RUN"))
            .mappings()
            .one()
        )
        assert row["payload"] == {} and row["target_id"] is None and row["reason_code"] == "RETENTION_REVIEW"
    assert all(t["status"] == "NOT_INSPECTED" for t in r.json()["not_inspected"])
    assert r.json()["business_data_modified"] is False and r.json()["minimal_audit_added"] is True


def test_audit_failure_rolls_back_preview(client, app, monkeypatch):
    f = app.state.session_factory
    grant(f)
    h = login_as(client, "admin")
    before = business_hashes(f)

    def fail(*a, **k):
        raise RuntimeError("PRIVATE_RETENTION_AUDIT_FAIL")

    monkeypatch.setattr(audit, "record", fail)
    r = client.post(URL, headers=h, json=BODY)
    assert r.status_code == 500 and "PRIVATE_RETENTION" not in r.text
    assert before == business_hashes(f)


def test_global_fixture_inventory_references_and_repeat_preserved(client, app, fixture_dir):
    f = app.state.session_factory
    with f.begin() as s:
        seed_fixture(s, fixture_dir)
    grant(f)
    before = business_hashes(f)
    r = client.post(URL, headers=login_as(client, "admin"), json=BODY)
    assert r.status_code == 200
    report = r.json()
    for name in [
        "messages",
        "ai_suggestions",
        "approvals",
        "followup_actions",
        "idempotency_keys",
        "audit_events",
        "analytics_receipts",
        "analytics_batches",
        "analytics_daily",
        "analytics_product_daily",
        "analytics_product_risk",
        "analytics_product_voc_daily",
        "customers",
        "knowledge_documents",
    ]:
        assert target(report, name)["inspection"] == "INSPECTED"
    assert target(report, "ai_suggestions")["inspected_count"] > 0
    # Fixture's October window is not a30-day expiry at its own source_as_of.
    assert target(report, "ai_suggestions")["past_retention_count"] == 0
    assert target(report, "knowledge_documents")["undetermined_count"] > 0
    assert before == business_hashes(f)
    with f.begin() as s:
        assert sum(seed_fixture(s, fixture_dir)["inserted"].values()) == 0


def test_retention_migration_no_grants_and_guarded_recovery(settings, monkeypatch):
    migrate(settings, monkeypatch, "0005")
    engine = build_engine(settings)
    factory = session_factory(engine)
    from app.seed import seed_minimal
    from app.staff_models import staff_permissions

    with factory.begin() as s:
        seed_minimal(s, "REVIEW_PW_05c17ba08dbe599cfeeee1c")
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    command.check(Config(str(ROOT / "alembic.ini")))
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(staff_permissions)) == 0
    command.downgrade(Config(str(ROOT / "alembic.ini")), "0005")
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    grant(factory)
    with pytest.raises(RuntimeError, match="retention review"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0005")
    engine.dispose()


def test_retention_audit_blocks_downgrade_even_without_current_grant(client, app):
    with app.state.session_factory.begin() as s:
        audit.record(
            s, stable_id("admin"), "RETENTION_DRY_RUN", "RETENTION_REVIEW", None, reason="RETENTION_REVIEW"
        )
    with pytest.raises(RuntimeError, match="retention review"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0005")
    assert client.get("/health/ready").status_code == 200
