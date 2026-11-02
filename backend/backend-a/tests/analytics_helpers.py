from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from app.analytics_auth import AUDIENCE, ISSUER
from app.analytics_canonical import canonical_submission, table_hashes
from app.analytics_schemas import Submission
from app.seed import stable_id

ROOT = "/api/v1/analytics/batches"
READ = "/api/v1/admin/analytics"


def service_headers(app, permissions=None):
    settings = app.state.settings
    settings.analytics_service_secret = "REVIEW_KEY_db5b85763364fa7c06034f1482c50e02f0dd131e6"
    settings.analytics_service_ids = ["local-contract-test"]
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "local-contract-test",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=5),
            "permissions": permissions
            if permissions is not None
            else ["analytics:receive", "analytics:publish"],
        },
        settings.analytics_service_secret,
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


def rehash(body):
    submission = Submission.model_validate(body)
    value = canonical_submission(submission)
    value["manifest"]["row_counts"] = {t: len(rows) for t, rows in value["payload"].items()}
    value["manifest"]["payload_checksums"] = table_hashes(value["payload"])
    return value


def small_batch():
    team, product = stable_id("team"), stable_id("product")
    # Use product from minimal seed (confirmed by test setup below).
    m = {
        "batch_id": str(uuid4()),
        "schema_version": "analytics-v1",
        "rule_version": "voc_rule_v1",
        "source": "LOCAL_SYNTHETIC",
        "source_as_of": "2026-10-31T03:00:00Z",
        "generated_at": "2026-10-31T03:00:00Z",
        "windows": {
            "history_start": "2026-10-02T15:00:00Z",
            "operational_start": "2026-10-02T15:00:00Z",
            "sales_start": "2026-10-02T15:00:00Z",
            "prior_start": "2026-10-16T15:00:00Z",
            "recent_start": "2026-10-23T15:00:00Z",
            "window_end": "2026-10-30T15:00:00Z",
        },
        "team_ids": [team],
        "product_ids": [product],
        "scopes": [{"scope_key": "T1", "team_ids": [team]}],
        "row_counts": {
            t: 0
            for t in (
                "analytics_daily",
                "analytics_product_daily",
                "analytics_product_voc_daily",
                "analytics_product_risk",
            )
        },
        "payload_checksums": {
            t: "0" * 64
            for t in (
                "analytics_daily",
                "analytics_product_daily",
                "analytics_product_voc_daily",
                "analytics_product_risk",
            )
        },
        "source_input_hashes": {},
        "kpi_definition": "fixture-ticket-v1",
        "product_kpi_definition": "issue-tag-grain-v1",
        "sales_denominator_scope": "GLOBAL_PRODUCT_PAID_28D",
    }
    metrics = {
        "C": 5,
        "P": 1,
        "S": 100,
        "N": 4,
        "M": 1,
        "U": 2,
        "K": 3,
        "raw_rate": 0.05,
        "smoothed_rate": 0.05,
        "growth": 4,
        "top_issue": "DAMAGED",
        "outside_cohort": 0,
        "excluded_count": 0,
        "sales_complete": True,
        "quality_ok": True,
        "complaints_complete": True,
        "episode_state_complete": True,
    }
    return rehash(
        {
            "manifest": m,
            "payload": {
                "analytics_daily": [
                    {
                        "day": "2026-10-30",
                        "team_key": team,
                        "category": "PRODUCT",
                        "ticket_count": 10,
                        "auto_closed_count": 4,
                        "handoff_count": 6,
                        "reopened_count": 0,
                        "sla_breach_count": 0,
                        "duration_sum_seconds": 120,
                        "duration_n": 3,
                        "approval_count": 0,
                        "review_count": 0,
                    }
                ],
                "analytics_product_daily": [],
                "analytics_product_voc_daily": [
                    {
                        "scope_key": "T1",
                        "product_id": product,
                        "day": "2026-10-30",
                        "primary_issue": "DAMAGED",
                        "episode_count": 5,
                        "unresolved_count": 2,
                    }
                ],
                "analytics_product_risk": [
                    {
                        "scope_key": "T1",
                        "product_id": product,
                        "rule_version": "voc_rule_v1",
                        "data_status": "ELIGIBLE",
                        "score": "50",
                        "rank": 1,
                        "risk_band": "WATCH",
                        "metrics": metrics,
                        "components": {
                            k: {"normalized": 0.5, "weight": w, "contribution": 50 * w}
                            for k, w in (
                                ("volume", 0.1),
                                ("rate", 0.35),
                                ("growth", 0.25),
                                ("repeat", 0.2),
                                ("unresolved", 0.1),
                            )
                        },
                        "source_as_of": m["source_as_of"],
                        "window_end": m["windows"]["window_end"],
                    }
                ],
            },
        }
    )


def stage(client, app, body=None):
    body = body or small_batch()
    h = service_headers(app)
    r = client.post(ROOT, json=body, headers=h)
    assert r.status_code == 200, r.text
    return body, h


def publish(client, app, body=None):
    body, h = stage(client, app, body)
    bid = body["manifest"]["batch_id"]
    r = client.post(f"{ROOT}/{bid}/validate", headers=h)
    assert r.status_code == 200 and r.json()["validation_passed"], r.text
    r = client.post(f"{ROOT}/{bid}/publish", headers=h)
    assert r.status_code == 200, r.text
    return body, h
