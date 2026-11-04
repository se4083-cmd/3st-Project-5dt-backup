from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text

from app.analytics_canonical import digest
from app.extensions.p1 import voc_provider
from app.extensions.p1.models import p1_idempotency
from app.extensions.p1.voc_models import voc_reviews
from app.model_constraints import user_team_scopes
from app.models import teams, users
from app.seed import stable_id
from tests.analytics_helpers import publish, rehash, small_batch
from tests.conftest import ROOT, login_as, migrate
from tests.phase6_helpers import grant
from tests.test_finalization_contract import require_postgres

BASE = "/api/v1/admin/p1/voc-proposals"


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("P1_ENABLED", "true")
    monkeypatch.setenv("P1_VOC_ENABLED", "true")
    monkeypatch.setenv("P1_VOC_PROVIDER", "MOCK")
    monkeypatch.setenv("P1_VOC_AZURE_ENABLED", "false")


def admin(client, app, *permissions):
    grant(app, "admin", *(permissions or ("P1_VOC_READ", "P1_VOC_GENERATE", "P1_VOC_REVIEW")))
    return login_as(client, "admin")


def evidence(client, app, mutate=None):
    app.state.settings.analytics_stale_hours = 720
    body = small_batch()
    rows = body["payload"]["analytics_product_voc_daily"]
    rows[0]["episode_count"] = 3
    rows[0]["unresolved_count"] = 1
    rows.append(dict(rows[0], day="2026-10-29", episode_count=2, unresolved_count=1))
    if mutate:
        mutate(body)
    body = rehash(body)
    publish(client, app, body)
    return body


def create(client, headers, key=None, **body):
    return client.post(
        BASE,
        headers={**headers, "Idempotency-Key": key or "voc-" + uuid4().hex},
        json={"product_id": stable_id("product"), "team_ids": [stable_id("team")], **body},
    )


def test_grounded_mock_generation_history_and_review(client, app):
    h = admin(client, app)
    batch = evidence(client, app)
    r = create(client, h)
    assert r.status_code == 201, r.text
    value = r.json()
    assert value["status"] == "PENDING_REVIEW" and value["provider"] == "MOCK"
    assert value["batch_id"] == batch["manifest"]["batch_id"]
    assert digest(value["evidence"]) == value["evidence_hash"]
    assert value["evidence"]["meta"]["source"] == "LOCAL_SYNTHETIC"
    assert value["evidence"]["fabric_connection"] == "UNVERIFIED"
    assert value["evidence"]["facts"]["rate"]["cohort_inquiry_ratio"] == 0.04
    assert len(value["evidence"]["facts"]["trend"]["daily"]) == 2
    assert value["evidence"]["meta"]["windows"] == batch["manifest"]["windows"]
    assert set(value["proposal"]["recommendations"][0]["evidence_ids"]) == {"risk", "repeat", "rate", "trend"}
    assert client.get(BASE + "/" + value["request_id"], headers=h).json() == value
    assert client.get(BASE, headers=h).json()["items"] == [value]
    review = {"expected_revision": 1, "decision": "APPROVED", "reason": "검증 실험 후보로 승인"}
    r = client.post(
        BASE + "/" + value["request_id"] + "/reviews",
        json=review,
        headers={**h, "Idempotency-Key": "review-case-01"},
    )
    assert r.status_code == 200, r.text
    approved = r.json()
    assert approved["status"] == "APPROVED" and approved["revision"] == 2
    assert approved["evidence"] == value["evidence"] and approved["proposal"] == value["proposal"]
    assert len(approved["reviews"]) == 1
    replay = client.post(
        BASE + "/" + value["request_id"] + "/reviews",
        json=review,
        headers={**h, "Idempotency-Key": "review-case-01"},
    )
    assert replay.json() == approved and replay.headers["Idempotency-Replayed"] == "true"
    review["decision"] = "REJECTED"
    assert (
        client.post(
            BASE + "/" + value["request_id"] + "/reviews",
            json=review,
            headers={**h, "Idempotency-Key": "review-case-02"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "reason", ["NO_PUBLISHED_BATCH", "STALE_ANALYTICS", "INSUFFICIENT_TREND", "LOW_SAMPLE", "QUALITY_BLOCKED"]
)
def test_missing_or_insufficient_data_never_calls_provider(client, app, monkeypatch, reason):
    h = admin(client, app)

    def mutate(body):
        risk = body["payload"]["analytics_product_risk"][0]
        if reason == "INSUFFICIENT_TREND":
            body["payload"]["analytics_product_voc_daily"] = [
                dict(body["payload"]["analytics_product_voc_daily"][0], episode_count=5, unresolved_count=2)
            ]
        if reason in {"LOW_SAMPLE", "QUALITY_BLOCKED"}:
            risk.update(data_status=reason, score=None, rank=None, risk_band=None)
            if reason == "LOW_SAMPLE":
                risk["metrics"]["S"] = 20
            else:
                risk["metrics"]["quality_ok"] = False

    if reason != "NO_PUBLISHED_BATCH":
        evidence(client, app, mutate)
    if reason == "STALE_ANALYTICS":
        app.state.settings.analytics_stale_hours = 1

    def forbidden(*args):
        pytest.fail("Insufficient data must not reach the provider")

    monkeypatch.setattr(voc_provider, "generate", forbidden)
    r = create(client, h)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "INSUFFICIENT_DATA" and r.json()["reason_code"] == reason
    assert r.json()["proposal"] is None
    assert (
        client.post(
            BASE + "/" + r.json()["request_id"] + "/reviews",
            headers={**h, "Idempotency-Key": "bad-review-01"},
            json={"expected_revision": 1, "decision": "APPROVED", "reason": "not allowed"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("role", ["customer1", "agent", "admin"])
def test_no_implicit_role_grants(client, app, role):
    h = login_as(client, role)
    assert create(client, h).status_code == 403
    assert client.get(BASE, headers=h).status_code == 403
    if role != "admin":
        grant(app, role, "P1_VOC_GENERATE", "P1_VOC_READ", "P1_VOC_REVIEW")
        assert create(client, h).status_code == 403


def test_flags_and_bearer_do_not_break_monitoring(client, app, monkeypatch):
    h = admin(client, app)
    assert client.get(BASE).status_code == 401
    monkeypatch.setenv("P1_VOC_ENABLED", "false")
    assert create(client, h).status_code == 503
    assert client.get("/health/ready").status_code == 200
    grant(app, "admin", "P1_MONITOR_READ")
    assert client.get("/api/v1/admin/p1/monitoring/summary", headers=h).status_code == 200
    monkeypatch.setenv("P1_VOC_ENABLED", "true")
    monkeypatch.setenv("P1_ENABLED", "false")
    assert create(client, h).status_code == 503


def test_idempotency_reuses_one_generation_and_conflicts_on_different_body(client, app, monkeypatch):
    h = admin(client, app)
    evidence(client, app)
    original = voc_provider.generate
    calls = []

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(voc_provider, "generate", counted)
    first = create(client, h, "same-key-001")
    replay = create(client, h, "same-key-001")
    assert replay.status_code == 200 and replay.json() == first.json()
    assert calls == [1]
    assert create(client, h, "same-key-001", product_id=str(uuid4())).status_code == 409
    grant(app, "admin", "P1_MONITOR_READ")
    with app.state.session_factory.begin() as s:
        from app.staff_models import staff_permissions

        s.execute(staff_permissions.delete().where(staff_permissions.c.permission == "P1_VOC_GENERATE"))
    assert create(client, h, "same-key-001").status_code == 403


def test_scope_revocation_hides_history_and_review_and_replay(client, app):
    h = admin(client, app)
    evidence(client, app)
    value = create(client, h, "scope-key-01").json()
    with app.state.session_factory.begin() as s:
        s.execute(
            teams.insert().values(
                team_id=stable_id("other-team"), name="other", supported_categories=[], active=True
            )
        )
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
        s.execute(
            user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=stable_id("other-team"))
        )
    assert client.get(BASE, headers=h).json()["items"] == []
    assert client.get(BASE + "/" + value["request_id"], headers=h).status_code == 404
    assert create(client, h, "scope-key-01").status_code == 403
    assert (
        client.post(
            BASE + "/" + value["request_id"] + "/reviews",
            headers={**h, "Idempotency-Key": "scope-review01"},
            json={"expected_revision": 1, "decision": "REJECTED", "reason": "out of scope"},
        ).status_code
        == 404
    )


def test_independent_permissions_validation_and_history_pagination(client, app):
    h = admin(client, app, "P1_VOC_GENERATE")
    evidence(client, app)
    for _ in range(3):
        assert create(client, h).status_code == 201
    assert client.get(BASE, headers=h).status_code == 403
    grant(app, "admin", "P1_VOC_READ")
    page = client.get(BASE, headers=h, params={"limit": 2}).json()
    next_ = client.get(BASE, headers=h, params={"limit": 2, "cursor": page["next_cursor"]}).json()
    assert len({i["request_id"] for i in page["items"] + next_["items"]}) == 3
    assert client.get(BASE, headers=h, params={"cursor": "bad"}).status_code == 422
    assert create(client, h, team_ids=[stable_id("team")] * 2).status_code == 422
    assert create(client, h, team_ids=[str(uuid4())]).status_code == 403
    r = client.post(
        BASE, json={"product_id": stable_id("product"), "team_ids": [stable_id("team")]}, headers=h
    )
    assert r.status_code == 422
    assert create(client, h, period="invented").status_code == 422
    r = client.post(
        BASE + "/" + page["items"][0]["request_id"] + "/reviews",
        headers={**h, "Idempotency-Key": "read-no-review"},
        json={"expected_revision": 1, "decision": "APPROVED", "reason": "hello"},
    )
    assert r.status_code == 403


def test_provider_failure_is_persisted_safely_without_silent_mock_fallback(client, app, monkeypatch):
    h = admin(client, app)
    evidence(client, app)
    monkeypatch.setenv("P1_VOC_PROVIDER", "AZURE_OPENAI")
    # Explicit Azure enable is absent: no opener may be constructed.
    monkeypatch.setattr(voc_provider, "build_opener", lambda *a: pytest.fail("Azure disabled"))
    result = create(client, h).json()
    assert result["status"] == "FAILED" and result["reason_code"] == "AZURE_CALLS_DISABLED"
    assert result["provider"] == "AZURE_OPENAI" and result["proposal"] is None
    assert "api_key" not in str(result)


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
def test_review_requires_current_revision_and_nonblank_reason(client, app, decision):
    h = admin(client, app)
    evidence(client, app)
    value = create(client, h).json()
    path = BASE + "/" + value["request_id"] + "/reviews"
    assert (
        client.post(
            path,
            headers={**h, "Idempotency-Key": "review-invalid1"},
            json={"expected_revision": 8, "decision": decision, "reason": "reviewed"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            path,
            headers={**h, "Idempotency-Key": "review-invalid1"},
            json={"expected_revision": 1, "decision": decision, "reason": "   "},
        ).status_code
        == 422
    )
    r = client.post(
        path,
        headers={**h, "Idempotency-Key": "review-valid001"},
        json={"expected_revision": 1, "decision": decision, "reason": "reviewed"},
    )
    assert r.status_code == 200 and r.json()["status"] == decision
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(voc_reviews)) == 1
        assert s.scalar(select(func.count()).select_from(p1_idempotency)) == 2


@pytest.mark.postgres
def test_concurrent_same_key_calls_provider_once(client, app, monkeypatch):
    require_postgres(app)
    h = admin(client, app)
    evidence(client, app)
    original = voc_provider.generate
    calls = []

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(voc_provider, "generate", counted)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(client, h, "concurrent-voc01"), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert len({r.json()["request_id"] for r in responses}) == 1 and calls == [1]


def test_0008_upgrade_empty_roundtrip_and_data_loss_guard(settings, monkeypatch):
    migrate(settings, monkeypatch, "0008")
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "0008")
    command.upgrade(config, "head")


def test_downgrade_refuses_proposal_history(client, app):
    h = admin(client, app)
    create(client, h)  # insufficient records also cannot be discarded
    with pytest.raises(RuntimeError, match="retain 0009"):
        command.downgrade(Config(str(ROOT / "alembic.ini")), "0008")
    with app.state.engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0009"


def test_existing_p1_monitoring_openapi_is_unchanged(app):
    import json

    baseline = json.loads((ROOT / "docs/p1-monitoring-contract.json").read_text())
    actual = app.openapi()
    for path, operation in baseline["paths"].items():
        assert actual["paths"][path] == operation
    for kind, definitions in baseline["components"].items():
        for name, schema in definitions.items():
            assert actual["components"][kind][name] == schema


def test_generation_and_review_do_not_change_any_p0_business_rows(client, app):
    from app.schema import metadata

    h = admin(client, app)
    evidence(client, app)
    tables = [t for t in metadata.sorted_tables if not t.name.startswith("p1_") and t.name != "audit_events"]

    def snapshot():
        with app.state.session_factory() as s:
            return {
                t.name: [dict(r) for r in s.execute(select(t).order_by(*t.primary_key.columns)).mappings()]
                for t in tables
            }

    before = snapshot()
    result = create(client, h).json()
    r = client.post(
        BASE + "/" + result["request_id"] + "/reviews",
        json={"expected_revision": 1, "decision": "APPROVED", "reason": "human review"},
        headers={**h, "Idempotency-Key": "no-business-effect"},
    )
    assert r.status_code == 200
    assert snapshot() == before


def test_0009_preserves_existing_p0_and_p1_rows(settings, monkeypatch):
    from app.db import build_engine, session_factory, utcnow
    from app.extensions.p1.models import p1_tasks
    from app.schema import metadata
    from app.seed import seed_minimal
    from app.staff_models import staff_permissions
    from tests.conftest import PASSWORD
    from tests.p1.test_migrations import task

    migrate(settings, monkeypatch, "0008")
    engine = build_engine(settings)
    factory = session_factory(engine)
    try:
        with factory.begin() as s:
            seed_minimal(s, PASSWORD)
            s.execute(
                staff_permissions.insert().values(user_id=stable_id("admin"), permission="P1_MONITOR_READ")
            )
            s.execute(p1_tasks.insert().values(**task()))
            s.execute(
                p1_idempotency.insert().values(
                    user_id=stable_id("admin"),
                    operation="VOC_GENERATE",
                    key="legacy-key-01",
                    request_hash="a" * 64,
                    response_status=201,
                    response_snapshot={},
                    created_at=utcnow(),
                )
            )
        tables = [t for t in metadata.sorted_tables if not t.name.startswith("p1_voc_")]

        def snapshot():
            with factory() as s:
                return {
                    t.name: [
                        dict(r) for r in s.execute(select(t).order_by(*t.primary_key.columns)).mappings()
                    ]
                    for t in tables
                }

        before = snapshot()
        config = Config(str(ROOT / "alembic.ini"))
        command.upgrade(config, "head")
        command.check(config)
        assert snapshot() == before
        command.downgrade(config, "0008")
        assert snapshot() == before
        command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_invalid_provider_output_creates_failure_without_draft(client, app, monkeypatch):
    h = admin(client, app)
    evidence(client, app)
    monkeypatch.setenv("P1_VOC_PROVIDER", "AZURE_OPENAI")
    monkeypatch.setattr(
        voc_provider,
        "azure_json",
        lambda *a: {"recommendations": [{"title": "bad", "action": "invented", "evidence_ids": ["unknown"]}]},
    )
    r = create(client, h)
    assert r.status_code == 201 and r.json()["status"] == "FAILED"
    assert r.json()["reason_code"] == "AI_INVALID_OUTPUT" and r.json()["proposal"] is None


def test_partial_team_revocation_hides_full_scope_record(client, app):
    h = admin(client, app)
    other = stable_id("second-team")
    with app.state.session_factory.begin() as s:
        s.execute(teams.insert().values(team_id=other, name="second", supported_categories=[], active=True))
        s.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=other))
    created = create(client, h, team_ids=[stable_id("team"), other])
    assert created.status_code == 201
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.team_id == other))
    assert client.get(BASE, headers=h).json()["items"] == []
    assert client.get(BASE + "/" + created.json()["request_id"], headers=h).status_code == 404


@pytest.mark.postgres
def test_concurrent_review_records_one_decision(client, app):
    require_postgres(app)
    h = admin(client, app)
    evidence(client, app)
    value = create(client, h).json()
    path = BASE + "/" + value["request_id"] + "/reviews"

    def decide(decision):
        return client.post(
            path,
            headers={**h, "Idempotency-Key": "decision-" + decision},
            json={"expected_revision": 1, "decision": decision, "reason": "reviewed"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(decide, ["APPROVED", "REJECTED"]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(voc_reviews)) == 1


def test_deactivated_account_and_revoked_review_grant(client, app):
    from app.staff_models import staff_permissions

    h = admin(client, app)
    evidence(client, app)
    value = create(client, h).json()
    with app.state.session_factory.begin() as s:
        s.execute(staff_permissions.delete().where(staff_permissions.c.permission == "P1_VOC_REVIEW"))
    assert (
        client.post(
            BASE + "/" + value["request_id"] + "/reviews",
            headers={**h, "Idempotency-Key": "revoked-review1"},
            json={"expected_revision": 1, "decision": "APPROVED", "reason": "blocked"},
        ).status_code
        == 403
    )
    with app.state.session_factory.begin() as s:
        s.execute(users.update().where(users.c.user_id == stable_id("admin")).values(active=False))
    assert client.get(BASE, headers=h).status_code == 401
