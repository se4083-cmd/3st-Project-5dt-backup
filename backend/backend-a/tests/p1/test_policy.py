import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text

from app.analytics_canonical import digest
from app.extensions.p1.policy_models import policy_reviews
from app.model_constraints import user_team_scopes
from app.models import ai_suggestions, knowledge_documents, teams, tickets
from app.seed import stable_id
from tests.conftest import ROOT, login_as, migrate
from tests.phase6_helpers import grant, material_fixture
from tests.test_finalization_contract import require_postgres
from tests.test_flow import submit

BASE = "/api/v1/admin/p1"


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("P1_ENABLED", "true")
    monkeypatch.setenv("P1_POLICY_ENABLED", "true")


def admin(client, app, *permissions):
    grant(app, "admin", *(permissions or ("P1_POLICY_READ", "P1_POLICY_WRITE", "P1_POLICY_REVIEW")))
    return login_as(client, "admin")


def post(client, path, h, body, key=None):
    return client.post(
        BASE + path, headers={**h, "Idempotency-Key": key or "policy-" + uuid4().hex}, json=body
    )


def register(client, h, key=None, **overrides):
    return post(
        client,
        "/policies",
        h,
        {
            "policy_key": "POLICY_SAMPLE",
            "team_ids": [stable_id("team")],
            "title": "배송 안내",
            "body": "배송 안내\n기존 절차\n",
            **overrides,
        },
        key,
    )


def append(client, h, pid, key=None, **overrides):
    return post(
        client,
        f"/policies/{pid}/versions",
        h,
        {"expected_previous_version": 1, "title": "배송 안내", "body": "배송 안내\n변경 절차\n", **overrides},
        key,
    )


def compare(client, h, pid, old, new, key=None):
    return post(
        client, f"/policies/{pid}/comparisons", h, {"from_version_id": old, "to_version_id": new}, key
    )


def pair(client, h):
    a = register(client, h).json()
    pid = a["policy_id"]
    b = append(client, h, pid).json()
    c = compare(client, h, pid, a["versions"][0]["version_id"], b["version_id"])
    assert c.status_code == 201, c.text
    return pid, a["versions"][0], b, c.json()


def review(client, h, cid, key=None, **overrides):
    return post(
        client,
        f"/policy-comparisons/{cid}/reviews",
        h,
        {"expected_revision": 1, "decision": "APPROVED", "reason": "담당자 검토 완료", **overrides},
        key,
    )


def source(client, headers, app, faq=False):
    tid = submit(client, headers, order=stable_id("customer1/order/0")).json()["ticket_id"]
    tid, sid, aid, did, rid = material_fixture(app.state.session_factory, tid, synthetic=True)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(team_id=stable_id("team")))
        if faq:
            s.execute(
                ai_suggestions.update().where(ai_suggestions.c.suggestion_id == sid).values(category="FAQ")
            )
            s.execute(
                knowledge_documents.update()
                .where(knowledge_documents.c.document_id == did)
                .values(allowed_topics=["FAQ"])
            )
    return tid, did, sid


def source_comparison(client, h, did):
    a = register(client, h, policy_key="LOCAL_POLICY", body="PRIVATE_POLICY_BODY", source_document_id=did)
    assert a.status_code == 201, a.text
    a = a.json()
    pid = a["policy_id"]
    b = append(client, h, pid).json()
    c = compare(client, h, pid, a["versions"][0]["version_id"], b["version_id"])
    assert c.status_code == 201, c.text
    return c.json()


def test_version_diff_review_and_immutable_history(client, app):
    h = admin(client, app)
    pid, a, b, c = pair(client, h)
    assert c["diff"]["kind"] == "CONTENT_CHANGED"
    assert c["diff"]["changes"][0]["operation"] == "replace"
    assert digest({"diff": c["diff"], "impact": c["impact"]}) == c["analysis_hash"]
    assert c["impact"]["auto_replies"]["status"] == "UNCONFIRMED"
    assert c["impact"]["auto_replies"]["actual_affected_count"] is None
    assert c["activation"] == "NOT_SUPPORTED" and c["reviewable"]
    r = review(client, h, c["comparison_id"], "policy-review-01")
    assert r.status_code == 200, r.text
    approved = r.json()
    assert approved["status"] == approved["candidate_status"] == "APPROVED"
    assert approved["diff"] == c["diff"] and approved["impact"] == c["impact"]
    assert len(approved["reviews"]) == 1 and not approved["reviewable"]
    assert review(client, h, c["comparison_id"], "policy-review-01").json() == approved
    assert review(client, h, c["comparison_id"]).status_code == 409
    assert (
        client.get(BASE + f"/policies/{pid}/versions/{b['version_id']}", headers=h).json()["status"]
        == "APPROVED"
    )
    assert (
        client.get(BASE + f"/policies/{pid}/versions/{a['version_id']}", headers=h).json()["body"]
        == a["body"]
    )
    assert len(client.get(BASE + f"/policies/{pid}/comparisons", headers=h).json()["items"]) == 1


@pytest.mark.parametrize(
    "body,title,kind",
    [
        ("배송 안내\n기존 절차\n", "배송 안내", "NO_CHANGE"),
        ("배송 안내\n기존 절차\n", "제목 변경", "METADATA_ONLY"),
        ("배송 안내\n추가 안내\n기존 절차\n", "배송 안내", "CONTENT_CHANGED"),
    ],
)
def test_no_change_metadata_and_partial_change(client, app, body, title, kind):
    h = admin(client, app)
    a = register(client, h).json()
    pid = a["policy_id"]
    b = append(client, h, pid, body=body, title=title).json()
    r = compare(client, h, pid, a["versions"][0]["version_id"], b["version_id"])
    assert r.status_code == 201 and r.json()["diff"]["kind"] == kind
    if kind == "NO_CHANGE":
        assert not r.json()["diff"]["changes"]


def test_initial_comparison_and_rejection(client, app):
    h = admin(client, app)
    a = register(client, h).json()
    v = a["versions"][0]
    c = compare(client, h, a["policy_id"], None, v["version_id"]).json()
    assert c["diff"]["kind"] == "INITIAL_VERSION"
    r = review(client, h, c["comparison_id"], decision="REJECTED")
    assert r.status_code == 200 and r.json()["candidate_status"] == "REJECTED"


def test_optimistic_append_idempotency_and_pair_conflicts(client, app):
    h = admin(client, app)
    a = register(client, h, "register-key-01")
    pid = a.json()["policy_id"]
    assert register(client, h, "register-key-01").json() == a.json()
    assert register(client, h, "register-key-01", body="different").status_code == 409
    assert register(client, h).status_code == 409
    b = append(client, h, pid, "version-key-01")
    assert b.status_code == 201
    assert append(client, h, pid, "version-key-01").json() == b.json()
    assert append(client, h, pid).status_code == 409
    old = a.json()["versions"][0]["version_id"]
    new = b.json()["version_id"]
    assert compare(client, h, pid, new, old).status_code == 422
    assert compare(client, h, pid, old, old).status_code == 422
    assert compare(client, h, pid, None, new).status_code == 422
    c = compare(client, h, pid, old, new, "compare-key-01")
    assert compare(client, h, pid, old, new, "compare-key-01").json() == c.json()
    assert compare(client, h, pid, None, old, "compare-key-01").status_code == 409
    other = register(client, h, policy_key="OTHER").json()
    assert compare(client, h, pid, other["versions"][0]["version_id"], new).status_code == 404


@pytest.mark.parametrize("faq", [False, True])
def test_verified_historical_policy_references_and_rule_co_usage(client, headers, app, faq):
    h = admin(client, app)
    tid, did, sid = source(client, headers, app, faq)
    c = source_comparison(client, h, did)
    impact = c["impact"]
    assert impact["source_validation"] == "VERIFIED_SNAPSHOT"
    assert impact["auto_replies"]["observed_reference_count"] == 1
    assert impact["automation_rules"]["observed_reference_count"] == 1
    assert impact["automation_rules"]["links"][0]["rule_origin"] == "SYNTHETIC"
    assert impact["automation_rules"]["links"][0]["relation"] == "RULE_CO_USED_WITH_POLICY_CITATION"
    assert impact["faq"]["observed_reference_count"] == int(faq)
    assert (
        impact["faq_catalog"] == impact["rule_condition_dependency"] == impact["rag_index"] == "UNCONFIRMED"
    )
    assert impact["auto_replies"]["links"][0]["origin"] == "SYNTHETIC"
    assert "PRIVATE_" not in json.dumps(impact)


@pytest.mark.parametrize("mutation", ["body", "hash", "reference", "rule_version", "outside_team"])
def test_drift_invalid_refs_and_outside_scope_never_invent_verified_links(client, headers, app, mutation):
    h = admin(client, app)
    tid, did, sid = source(client, headers, app)
    a = register(
        client, h, policy_key="LOCAL_POLICY", body="PRIVATE_POLICY_BODY", source_document_id=did
    ).json()
    b = append(client, h, a["policy_id"]).json()
    with app.state.session_factory.begin() as s:
        if mutation == "body":
            s.execute(
                knowledge_documents.update()
                .where(knowledge_documents.c.document_id == did)
                .values(body="mutated")
            )
        elif mutation == "hash":
            s.execute(
                knowledge_documents.update()
                .where(knowledge_documents.c.document_id == did)
                .values(content_hash="b" * 64)
            )
        elif mutation == "reference":
            s.execute(
                ai_suggestions.update()
                .where(ai_suggestions.c.suggestion_id == sid)
                .values(evidence_refs=[{"document_id": did, "version": 99, "content_hash": "a" * 64}])
            )
        elif mutation == "rule_version":
            s.execute(
                ai_suggestions.update().where(ai_suggestions.c.suggestion_id == sid).values(rule_version=99)
            )
        else:
            other = stable_id("policy-outside-team")
            s.execute(
                teams.insert().values(team_id=other, name="outside", active=True, supported_categories=[])
            )
            s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(team_id=other))
    r = compare(client, h, a["policy_id"], a["versions"][0]["version_id"], b["version_id"])
    assert r.status_code == 201, r.text
    impact = r.json()["impact"]
    assert impact["automation_rules"]["observed_reference_count"] == 0
    assert impact["automation_rules"]["status"] == "UNCONFIRMED"
    if mutation != "rule_version":
        assert impact["auto_replies"]["observed_reference_count"] == 0
    if mutation in {"body", "hash"}:
        assert impact["source_validation"] == "UNCONFIRMED"


def test_import_requires_exact_key_and_content_and_no_inherited_usage(client, headers, app):
    h = admin(client, app)
    tid, did, sid = source(client, headers, app)
    assert register(client, h, source_document_id=did).status_code == 409
    a = register(
        client, h, policy_key="LOCAL_POLICY", source_document_id=did, body="PRIVATE_POLICY_BODY"
    ).json()
    pid = a["policy_id"]
    b = append(client, h, pid).json()
    assert b["source_document_id"] is None
    d = append(client, h, pid, expected_previous_version=2, body="third version").json()
    c = compare(client, h, pid, b["version_id"], d["version_id"]).json()
    assert c["impact"]["source_validation"] == "UNCONFIRMED"


@pytest.mark.parametrize("role", ["admin", "agent", "customer1"])
def test_no_implicit_policy_permission(client, app, role):
    h = login_as(client, role)
    assert register(client, h).status_code == 403
    assert client.get(BASE + "/policies", headers=h).status_code == 403
    if role != "admin":
        grant(app, role, "P1_POLICY_WRITE", "P1_POLICY_READ", "P1_POLICY_REVIEW")
        assert register(client, h).status_code == 403


def test_scope_revocation_blocks_replay_history_and_review(client, app):
    h = admin(client, app)
    pid, a, b, c = pair(client, h)
    other = stable_id("policy-second-team")
    with app.state.session_factory.begin() as s:
        s.execute(teams.insert().values(team_id=other, name="second", active=True, supported_categories=[]))
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
        s.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=other))
    assert client.get(BASE + "/policies", headers=h).json()["items"] == []
    assert client.get(BASE + f"/policies/{pid}", headers=h).status_code == 404
    hidden = client.get(BASE + f"/policy-comparisons/{c['comparison_id']}", headers=h)
    missing = client.get(BASE + f"/policy-comparisons/{uuid4()}", headers=h)
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["error"]["code"] == missing.json()["error"]["code"] == "POLICY_COMPARISON_NOT_FOUND"
    assert review(client, h, c["comparison_id"]).status_code == 404
    assert append(client, h, pid).status_code == 404


def test_partial_scope_revocation_and_immutable_scope(client, app):
    h = admin(client, app)
    other = stable_id("policy-second-team")
    with app.state.session_factory.begin() as s:
        s.execute(teams.insert().values(team_id=other, name="second", active=True, supported_categories=[]))
        s.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=other))
    a = register(client, h, team_ids=[stable_id("team"), other]).json()
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.team_id == other))
    assert client.get(BASE + f"/policies/{a['policy_id']}", headers=h).status_code == 404


def test_superseded_candidate_and_double_review_guard(client, app):
    h = admin(client, app)
    pid, a, b, c = pair(client, h)
    newer = append(client, h, pid, expected_previous_version=2).json()
    assert review(client, h, c["comparison_id"]).status_code == 409
    c1 = compare(client, h, pid, a["version_id"], newer["version_id"]).json()
    c2 = compare(client, h, pid, b["version_id"], newer["version_id"]).json()
    assert review(client, h, c1["comparison_id"]).status_code == 200
    assert review(client, h, c2["comparison_id"]).status_code == 409
    assert not client.get(BASE + f"/policy-comparisons/{c2['comparison_id']}", headers=h).json()["reviewable"]


def test_flags_permissions_validation_and_pagination(client, app, monkeypatch):
    h = admin(client, app, "P1_POLICY_WRITE")
    assert client.get(BASE + "/policies", headers=h).status_code == 403
    a = register(client, h).json()
    assert review(client, h, str(uuid4())).status_code == 403
    grant(app, "admin", "P1_POLICY_READ")
    for n in range(1, 4):
        append(client, h, a["policy_id"], expected_previous_version=n)
    page = client.get(BASE + f"/policies/{a['policy_id']}/versions", headers=h, params={"limit": 2}).json()
    next_ = client.get(
        BASE + f"/policies/{a['policy_id']}/versions",
        headers=h,
        params={"before_version": page["next_before_version"], "limit": 2},
    ).json()
    assert [v["version_no"] for v in page["items"] + next_["items"]] == [4, 3, 2, 1]
    assert register(client, h, team_ids=[stable_id("team")] * 2).status_code == 422
    assert register(client, h, body="   ").status_code == 422
    assert register(client, h, body="line\n" * 501).status_code == 422
    assert register(client, h, activate=True).status_code == 422
    assert client.get(BASE + "/policies").status_code == 401
    monkeypatch.setenv("P1_POLICY_ENABLED", "false")
    assert register(client, h).status_code == 503
    assert client.get("/health/ready").status_code == 200


def test_policy_approval_does_not_change_p0_or_existing_p1_rows(client, headers, app):
    from app.schema import metadata

    h = admin(client, app)
    tid, did, sid = source(client, headers, app)
    tables = [
        t
        for t in metadata.sorted_tables
        if not t.name.startswith("p1_polic") and t.name not in {"audit_events", "p1_idempotency"}
    ]

    def snapshot():
        with app.state.session_factory() as s:
            return {
                t.name: [dict(r) for r in s.execute(select(t).order_by(*t.primary_key.columns)).mappings()]
                for t in tables
            }

    before = snapshot()
    c = source_comparison(client, h, did)
    assert review(client, h, c["comparison_id"]).status_code == 200
    assert snapshot() == before


def test_old_p1_monitoring_and_voc_openapi_unchanged(app):
    baseline = json.loads((ROOT / "docs/p1-before-policy-contract.json").read_text())
    actual = app.openapi()
    for path, op in baseline["paths"].items():
        assert actual["paths"][path] == op
    for kind, definitions in baseline["components"].items():
        for name, schema in definitions.items():
            assert actual["components"][kind][name] == schema


def test_0010_empty_roundtrip_and_existing_data_preserved(settings, monkeypatch):
    from app.db import build_engine, session_factory
    from app.extensions.p1.models import p1_tasks
    from app.schema import metadata
    from app.seed import seed_minimal
    from tests.conftest import PASSWORD
    from tests.p1.test_migrations import task

    migrate(settings, monkeypatch, "0009")
    engine = build_engine(settings)
    factory = session_factory(engine)
    try:
        with factory.begin() as s:
            seed_minimal(s, PASSWORD)
            s.execute(p1_tasks.insert().values(**task()))
            from app.extensions.p1.voc_models import voc_requests, voc_teams

            request_id = str(uuid4())
            s.execute(
                voc_requests.insert().values(
                    request_id=request_id,
                    product_id=stable_id("product"),
                    created_by=stable_id("admin"),
                    status="INSUFFICIENT_DATA",
                    provider="MOCK",
                    evidence={},
                    evidence_hash=digest({}),
                    reason_code="NO_PUBLISHED_BATCH",
                )
            )
            s.execute(voc_teams.insert().values(request_id=request_id, team_id=stable_id("team")))

        tables = [t for t in metadata.sorted_tables if not t.name.startswith("p1_polic")]

        def snapshot():
            with factory() as s:
                return {
                    t.name: [
                        dict(r) for r in s.execute(select(t).order_by(*t.primary_key.columns)).mappings()
                    ]
                    for t in tables
                }

        before = snapshot()
        cfg = Config(str(ROOT / "alembic.ini"))
        command.upgrade(cfg, "head")
        command.check(cfg)
        assert snapshot() == before
        command.downgrade(cfg, "0009")
        assert snapshot() == before
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()


def test_downgrade_refuses_policy_history_and_offline(client, app):
    h = admin(client, app)
    register(client, h)
    cfg = Config(str(ROOT / "alembic.ini"))
    with pytest.raises(RuntimeError, match="retain 0010"):
        command.downgrade(cfg, "0009")
    with pytest.raises(RuntimeError, match="Offline"):
        command.downgrade(cfg, "0010:0009", sql=True)
    with app.state.engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0010"


@pytest.mark.postgres
def test_concurrent_appends_and_reviews_are_serialized(client, app):
    require_postgres(app)
    h = admin(client, app)
    a = register(client, h).json()
    pid = a["policy_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rs = list(pool.map(lambda _: append(client, h, pid), range(2)))
    assert sorted(r.status_code for r in rs) == [201, 409]
    b = next(r.json() for r in rs if r.status_code == 201)
    c = compare(client, h, pid, a["versions"][0]["version_id"], b["version_id"]).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        rs = list(
            pool.map(lambda d: review(client, h, c["comparison_id"], decision=d), ["APPROVED", "REJECTED"])
        )
    assert sorted(r.status_code for r in rs) == [200, 409]
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(policy_reviews)) == 1


@pytest.mark.postgres
def test_concurrent_registration_same_idempotency_key(client, app):
    require_postgres(app)
    h = admin(client, app)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rs = list(pool.map(lambda _: register(client, h, "same-policy-key-01"), range(2)))
    assert sorted(r.status_code for r in rs) == [200, 201]
    assert len({r.json()["policy_id"] for r in rs}) == 1


def test_revoked_review_permission_and_inactive_admin(client, app):
    from app.models import users
    from app.staff_models import staff_permissions

    h = admin(client, app)
    pid, old, new, comparison = pair(client, h)
    with app.state.session_factory.begin() as s:
        s.execute(staff_permissions.delete().where(staff_permissions.c.permission == "P1_POLICY_REVIEW"))
    assert review(client, h, comparison["comparison_id"]).status_code == 403
    with app.state.session_factory.begin() as s:
        s.execute(users.update().where(users.c.user_id == stable_id("admin")).values(active=False))
    assert client.get(BASE + f"/policies/{pid}", headers=h).status_code == 401


def test_review_bad_revision_blank_reason_and_independent_idempotency(client, app):
    h = admin(client, app)
    pid, old, new, comparison = pair(client, h)
    cid = comparison["comparison_id"]
    assert review(client, h, cid, expected_revision=9).status_code == 409
    assert review(client, h, cid, reason="   ").status_code == 422
    approved = review(client, h, cid, "review-fingerprint-01")
    assert approved.status_code == 200
    assert approved.headers["cache-control"] == "no-store"
    assert approved.headers["x-request-id"]
    assert review(client, h, cid, "review-fingerprint-01", decision="REJECTED").status_code == 409
