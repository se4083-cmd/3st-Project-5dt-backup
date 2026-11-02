from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app import audit, models
from app.analytics_models import analytics_receipts
from app.seed import seed_fixture, stable_id
from scripts.prepare_analytics_fixture import prepare
from tests.analytics_helpers import READ, ROOT, publish, rehash, service_headers, small_batch, stage
from tests.conftest import login_as


def test_initial_success_read_and_kpi(client, app):
    admin = login_as(client, "admin")
    r = client.get(READ + "/voc/top", headers=admin)
    assert r.json() == {
        "availability": "UNAVAILABLE",
        "reason": "NO_PUBLISHED_BATCH",
        "meta": None,
        "items": [],
    }
    body, h = publish(client, app)
    bid = body["manifest"]["batch_id"]
    top = client.get(READ + "/voc/top", headers=admin).json()
    assert top["meta"]["batch_id"] == bid and top["meta"]["source"] == "LOCAL_SYNTHETIC"
    assert top["items"][0]["score"] == "50.000000"
    detail = client.get(READ + "/products/" + stable_id("product"), headers=admin).json()
    assert detail["product"]["scope_key"] == top["meta"]["scope_key"] == detail["trend"][0]["scope_key"]
    kpi = client.get(READ + "/kpi", headers=admin).json()
    assert kpi["metrics"]["mean_duration_seconds"] == 40
    assert kpi["metrics"]["reopened"]["availability"] == "UNAVAILABLE"
    assert kpi["quality"] == "SYNTHETIC_APPROXIMATION"
    assert client.post(f"{ROOT}/{bid}/publish", headers=h).json()["is_current"]


@pytest.mark.parametrize("role", ["customer1", "agent", "admin"])
def test_user_cannot_publish_or_receive(client, app, role):
    service_headers(app)
    h = login_as(client, role)
    body = small_batch()
    assert client.post(ROOT, json=body, headers=h).status_code == 401
    assert client.post(f"{ROOT}/{uuid4()}/publish", headers=h).status_code == 401


@pytest.mark.parametrize("role", ["customer1", "agent"])
def test_non_admin_cannot_read(client, role):
    h = login_as(client, role)
    for route in ("/voc/top", "/voc/unavailable", "/kpi", "/products/" + stable_id("product")):
        assert client.get(READ + route, headers=h).status_code == 403


def test_service_permission_and_disabled_auth(client, app):
    assert client.post(ROOT, json=small_batch()).status_code == 503
    h = service_headers(app, ["analytics:receive"])
    assert client.post(f"{ROOT}/{uuid4()}/publish", headers=h).status_code == 403
    h = service_headers(app, ["analytics:publish"])
    assert client.post(ROOT, json=small_batch(), headers=h).status_code == 403


def test_retry_canonical_and_conflict(client, app):
    body, h = stage(client, app)
    reordered = {"payload": body["payload"], "manifest": dict(reversed(list(body["manifest"].items())))}
    first = client.post(ROOT, json=reordered, headers=h)
    assert first.status_code == 200
    changed = deepcopy(body)
    changed["payload"]["analytics_daily"][0]["ticket_count"] += 1
    assert client.post(ROOT, json=rehash(changed), headers=h).status_code == 409
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(analytics_receipts)) == 1


@pytest.mark.parametrize(
    "case,code",
    [
        ("checksum", "PAYLOAD_CHECKSUM"),
        ("count", "ROW_COUNT"),
        ("schema", "SCHEMA_VERSION"),
        ("rule", "RULE_VERSION"),
        ("duplicate", "DUPLICATE_PK"),
        ("fk", "PRODUCT_FK"),
        ("team", "TEAM_FK"),
        ("scope", "SCOPE_TEAMS"),
        ("same_scope", "SCOPE_SET_DUPLICATE"),
        ("rank", "RANK_ORDER"),
        ("band", "RISK_BAND"),
        ("null", "ELIGIBLE_VALUES"),
        ("status", "DATA_STATUS"),
        ("trend", "TREND_TOTAL"),
        ("window", "RULE_WINDOWS"),
        ("watermark", "RISK_WATERMARK"),
        ("component", "EXPLANATION_TOTAL"),
        ("weight", "EXPLANATION_WEIGHT"),
        ("daily", "DAILY_TEAM"),
    ],
)
def test_validation_blocks_invalid_payload(client, app, case, code):
    body = small_batch()
    m, p = body["manifest"], body["payload"]
    risk = p["analytics_product_risk"][0]
    if case == "schema":
        m["schema_version"] = "unknown"
    elif case == "rule":
        m["rule_version"] = "unknown"
    elif case == "duplicate":
        p["analytics_daily"].append(deepcopy(p["analytics_daily"][0]))
    elif case == "fk":
        m["product_ids"] = [str(uuid4())]
    elif case == "team":
        m["team_ids"] = [str(uuid4())]
    elif case == "scope":
        m["scopes"][0]["team_ids"] = [str(uuid4())]
    elif case == "same_scope":
        m["scopes"].append({"scope_key": "OTHER", "team_ids": m["team_ids"]})
    elif case == "rank":
        risk["rank"] = 2
    elif case == "band":
        risk["risk_band"] = "HIGH"
    elif case == "null":
        risk["score"] = None
    elif case == "status":
        risk["metrics"]["sales_complete"] = False
    elif case == "trend":
        p["analytics_product_voc_daily"][0]["episode_count"] += 1
    elif case == "window":
        m["windows"]["recent_start"] = "2026-10-24T15:00:00Z"
    elif case == "watermark":
        risk["source_as_of"] = "2026-10-30T15:00:00Z"
    elif case == "component":
        risk["components"]["volume"]["contribution"] = 9
    elif case == "weight":
        risk["components"]["volume"]["weight"] = 0.2
    elif case == "daily":
        p["analytics_daily"][0]["team_key"] = "NOT_A_TEAM"
    body = rehash(body)
    if case == "checksum":
        body["manifest"]["payload_checksums"]["analytics_daily"] = "a" * 64
    if case == "count":
        body["manifest"]["row_counts"]["analytics_daily"] = 2
    body, h = stage(client, app, body)
    bid = body["manifest"]["batch_id"]
    r = client.post(f"{ROOT}/{bid}/validate", headers=h)
    assert r.status_code == 200, r.text
    assert code in r.json()["validation_result"]["codes"]
    assert r.json()["status"] == "FAILED"
    assert client.post(f"{ROOT}/{bid}/publish", headers=h).status_code == 409
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(models.analytics_daily)) == 0


@pytest.mark.parametrize(
    "field", ["customer_id", "customer_key", "ticket_id", "message", "internal_note", "url", "path"]
)
def test_forbidden_fields_rejected_without_echo(client, app, field):
    body = small_batch()
    body["payload"]["analytics_product_risk"][0][field] = "SENSITIVE_SENTINEL"
    r = client.post(ROOT, json=body, headers=service_headers(app))
    assert r.status_code == 422 and "SENSITIVE_SENTINEL" not in r.text


def test_limits(client, app):
    app.state.settings.analytics_max_rows = 1
    assert client.post(ROOT, json=small_batch(), headers=service_headers(app)).status_code == 413
    # The middleware checks actual bytes rather than trusting Content-Length.
    r = client.post(ROOT, content=b" " * 8_000_001, headers=service_headers(app))
    assert r.status_code == 413


@pytest.mark.parametrize("action", ["receive", "validate", "publish"])
def test_audit_failure_rolls_back(client, app, monkeypatch, action):
    body, h = (small_batch(), service_headers(app)) if action == "receive" else stage(client, app)
    bid = body["manifest"]["batch_id"]
    if action == "publish":
        assert client.post(f"{ROOT}/{bid}/validate", headers=h).json()["validation_passed"]
    original = audit.record

    def fail(*args, **kwargs):
        if (
            args[2]
            == "ANALYTICS_" + {"receive": "RECEIVED", "validate": "VALIDATED", "publish": "PUBLISHED"}[action]
        ):
            raise RuntimeError("injected")
        return original(*args, **kwargs)

    monkeypatch.setattr(audit, "record", fail)
    r = (
        client.post(ROOT, json=body, headers=h)
        if action == "receive"
        else client.post(f"{ROOT}/{bid}/{action}", headers=h)
    )
    assert r.status_code == 500
    with app.state.session_factory() as s:
        row = (
            s.execute(select(models.analytics_batches).where(models.analytics_batches.c.batch_id == bid))
            .mappings()
            .first()
        )
        if action == "receive":
            assert row is None
        else:
            assert row["status"] == ("RECEIVED" if action == "validate" else "VALIDATED")
            if action == "validate":
                assert s.scalar(select(func.count()).select_from(models.analytics_product_risk)) == 0


def test_tampered_partial_load_cannot_publish(client, app):
    body, h = stage(client, app)
    bid = body["manifest"]["batch_id"]
    client.post(f"{ROOT}/{bid}/validate", headers=h)
    with app.state.session_factory.begin() as s:
        s.execute(
            models.analytics_product_risk.delete().where(models.analytics_product_risk.c.batch_id == bid)
        )
    r = client.post(f"{ROOT}/{bid}/publish", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "VALIDATED_PAYLOAD_CHANGED"


def test_failure_and_old_arrival_preserve_current(client, app):
    good, h = publish(client, app)
    bad = small_batch()
    bad["manifest"]["schema_version"] = "invalid"
    bad, _ = stage(client, app, bad)
    client.post(f"{ROOT}/{bad['manifest']['batch_id']}/validate", headers=h)
    assert client.post(f"{ROOT}/{bad['manifest']['batch_id']}/publish", headers=h).status_code == 409
    old, _ = stage(client, app)
    oldid = old["manifest"]["batch_id"]
    client.post(f"{ROOT}/{oldid}/validate", headers=h)
    assert client.post(f"{ROOT}/{oldid}/publish", headers=h).status_code == 409
    top = client.get(READ + "/voc/top", headers=login_as(client, "admin")).json()
    assert top["meta"]["batch_id"] == good["manifest"]["batch_id"]


def test_fixture_all_scopes_and_original_preserved(client, app, fixture_dir):
    import json

    from app.model_constraints import user_team_scopes

    with app.state.session_factory.begin() as s:
        seed_fixture(s, fixture_dir)
        for team in prepare(fixture_dir)["manifest"]["team_ids"]:
            s.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=team))
    body = prepare(fixture_dir)
    gold = json.loads((fixture_dir / "data/gold_voc_top_n.json").read_text(encoding="utf-8"))
    body, h = publish(client, app, body)
    admin = login_as(client, "admin")
    for scope in body["manifest"]["scopes"]:
        params = [("team_ids", t) for t in scope["team_ids"]]
        response = client.get(READ + "/voc/top", params=params, headers=admin)
        assert response.status_code == 200, response.text
        top = response.json()
        expected = sorted(
            (
                r
                for r in body["payload"]["analytics_product_risk"]
                if r["scope_key"] == scope["scope_key"] and r["rank"] is not None and r["rank"] <= 10
            ),
            key=lambda r: r["rank"],
        )
        assert [r["product_id"] for r in top["items"]] == [r["product_id"] for r in expected]
        assert [float(r["score"]) for r in top["items"]] == [float(r["score"]) for r in expected]
        original_top = sorted(
            (r for r in gold if r["scope_key"] == scope["scope_key"]), key=lambda r: r["rank"]
        )
        assert [(r["product_id"], float(r["score"]), r["rank"]) for r in top["items"]] == [
            (r["product_id"], r["score"], r["rank"]) for r in original_top
        ]
        assert top["meta"]["scope_key"] == scope["scope_key"]
        unavailable = client.get(READ + "/voc/unavailable", params=params, headers=admin).json()
        assert all(
            r["score"] is None and r["rank"] is None and r["risk_band"] is None for r in unavailable["items"]
        )
        pid = body["manifest"]["product_ids"][0]
        detail = client.get(READ + "/products/" + pid, params=params, headers=admin).json()
        assert detail["product"]["scope_key"] == scope["scope_key"]
        assert all(r["scope_key"] == scope["scope_key"] for r in detail["trend"])
        assert detail["product_kpi"]["availability"] == (
            "AVAILABLE" if len(scope["team_ids"]) == 4 else "UNAVAILABLE"
        )
    with app.state.session_factory.begin() as s:
        assert sum(seed_fixture(s, fixture_dir)["inserted"].values()) == 0
        assert s.scalar(select(func.count()).select_from(models.analytics_product_risk)) == 600
        original = (
            s.execute(
                select(models.analytics_batches).where(
                    models.analytics_batches.c.batch_id != body["manifest"]["batch_id"]
                )
            )
            .mappings()
            .one()
        )
        assert original["status"] == "VALIDATED" and not original["is_current"]


def test_scope_permissions_and_unpublished_pin(client, app):
    body, _ = publish(client, app)
    admin = login_as(client, "admin")
    assert client.get(READ + "/voc/top", params={"team_ids": str(uuid4())}, headers=admin).status_code == 403
    # Unknown scope_key is never used as an authorization input.
    assert (
        client.get(READ + "/voc/top", params={"scope_key": "ALL4"}, headers=admin).json()["meta"]["scope_key"]
        == "T1"
    )
    pending, _ = stage(client, app)
    assert (
        client.get(
            READ + "/voc/top", params={"batch_id": pending["manifest"]["batch_id"]}, headers=admin
        ).status_code
        == 404
    )
    from app.model_constraints import user_team_scopes

    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
    assert (
        client.get(
            READ + "/voc/top", params={"batch_id": body["manifest"]["batch_id"]}, headers=admin
        ).status_code
        == 403
    )


@pytest.mark.parametrize("data_status", ["LOW_SAMPLE", "DATA_MISSING", "QUALITY_BLOCKED"])
def test_noneligible_null_contract_and_exclusion_reason(client, app, data_status):
    body = small_batch()
    risk = body["payload"]["analytics_product_risk"][0]
    risk.update(data_status=data_status, score=None, rank=None, risk_band=None)
    if data_status == "LOW_SAMPLE":
        risk["metrics"]["S"] = 20
    elif data_status == "DATA_MISSING":
        risk["metrics"]["sales_complete"] = False
    else:
        risk["metrics"]["quality_ok"] = False
    body, h = publish(client, app, rehash(body))
    admin = login_as(client, "admin")
    assert client.get(READ + "/voc/top", headers=admin).json()["items"] == []
    item = client.get(READ + "/voc/unavailable", headers=admin).json()["items"][0]
    assert item["data_status"] == data_status and item["score"] is None and item["risk_band"] is None
    # Same upstream content with non-null score is rejected rather than made zero.
    from tests.test_analytics_database import newer

    bad = newer(body)
    bad["payload"]["analytics_product_risk"][0]["score"] = "0"
    bad, _ = stage(client, app, rehash(bad))
    result = client.post(f"{ROOT}/{bad['manifest']['batch_id']}/validate", headers=h).json()
    assert "NONELIGIBLE_NULLS" in result["validation_result"]["codes"]


def test_exact_scope_missing_never_falls_back_and_pin_permission(client, app, fixture_dir):
    from app.model_constraints import user_team_scopes

    with app.state.session_factory.begin() as s:
        seed_fixture(s, fixture_dir)
    body, _ = publish(client, app, prepare(fixture_dir))
    admin = login_as(client, "admin")
    # The minimal admin team has no exact aggregate, although ALL4 exists.
    result = client.get(READ + "/voc/top", headers=admin).json()
    assert result["reason"] == "SCOPE_NOT_PROVIDED" and result["items"] == []
    first_team = body["manifest"]["team_ids"][0]
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
        s.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=first_team))
    result = client.get(READ + "/voc/top", headers=admin).json()
    assert result["meta"]["team_ids"] == [first_team]
    for suffix in ("/voc/top", "/voc/unavailable", "/kpi", "/products/" + body["manifest"]["product_ids"][0]):
        r = client.get(
            READ + suffix,
            params=[
                ("team_ids", first_team),
                ("team_ids", body["manifest"]["team_ids"][1]),
                ("batch_id", body["manifest"]["batch_id"]),
            ],
            headers=admin,
        )
        assert r.status_code == 403


def test_rank_ties_use_upstream_c_then_product_uuid(client, app):
    from tests.test_analytics_database import newer

    body = small_batch()
    original = stable_id("product")
    other = str(uuid4())
    with app.state.session_factory.begin() as s:
        row = dict(
            s.execute(select(models.products).where(models.products.c.product_id == original))
            .mappings()
            .one()
        )
        row.update(product_id=other, sku="TIE-CONTRACT-PRODUCT")
        s.execute(models.products.insert().values(**row))
    body["manifest"]["product_ids"].append(other)
    risk = deepcopy(body["payload"]["analytics_product_risk"][0])
    risk["product_id"] = other
    body["payload"]["analytics_product_risk"].append(risk)
    trend = deepcopy(body["payload"]["analytics_product_voc_daily"][0])
    trend["product_id"] = other
    body["payload"]["analytics_product_voc_daily"].append(trend)
    for rank, r in enumerate(
        sorted(body["payload"]["analytics_product_risk"], key=lambda r: r["product_id"]), 1
    ):
        r["rank"] = rank
    body, h = publish(client, app, rehash(body))
    top = client.get(READ + "/voc/top", headers=login_as(client, "admin")).json()["items"]
    assert [r["product_id"] for r in top] == sorted([original, other])
    bad = newer(body)
    for r in bad["payload"]["analytics_product_risk"]:
        r["rank"] = 3 - r["rank"]
    bad, _ = stage(client, app, rehash(bad))
    assert (
        "RANK_ORDER"
        in client.post(f"{ROOT}/{bad['manifest']['batch_id']}/validate", headers=h).json()[
            "validation_result"
        ]["codes"]
    )
