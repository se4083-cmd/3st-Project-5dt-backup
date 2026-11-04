"""Make tiny synthetic documentation examples only; never read a DB or upload files."""

import hashlib
import hmac
import json
import shutil
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from app.analytics_canonical import canonical_submission, digest  # noqa: E402
from app.analytics_schemas import Submission  # noqa: E402

OUT = ROOT / "docs/fabric-data-contract/samples"
T = "2026-10-31T03:00:00.000000Z"


def uid(label):
    return str(uuid5(NAMESPACE_URL, "csflow-documentation-only/" + label))


def save(name, obj):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def jsonl(name, rows):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(
        b"".join(
            (
                json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                + "\n"
            ).encode("utf-8")
            for r in rows
        )
    )
    return {
        "object_key": name,
        "row_count": len(rows),
        "byte_count": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }


def main():
    team, customer, user, admin, product, order, ticket, action, event = map(
        uid, ["team", "customer", "customer-user", "admin", "product", "order", "ticket", "followup", "event"]
    )
    rows = {
        "teams": [dict(team_id=team, name="합성 문서팀", supported_categories=["DELIVERY"], active=True)],
        "users": [
            dict(user_id=user, role="CUSTOMER", team_id=None, allowed_team_ids=[], active=True),
            dict(user_id=admin, role="ADMIN", team_id=None, allowed_team_ids=[team], active=True),
        ],
        "customers": [dict(customer_id=customer, user_id=user, deleted_at=None)],
        "products": [
            dict(
                product_id=product,
                sku="SYNTHETIC-DOC-1",
                name="합성 문서 상품",
                category="생활용품",
                active=True,
            )
        ],
        "orders": [
            dict(
                order_id=order,
                customer_id=customer,
                product_id=product,
                quantity=1,
                order_status="DELIVERED",
                payment_status="PAID",
                amount="10000.00",
                placed_at=T,
                paid_at=T,
                version=1,
            )
        ],
        "tickets": [
            dict(
                ticket_id=ticket,
                customer_id=customer,
                order_id=order,
                product_id=product,
                team_id=team,
                category="DELIVERY",
                priority="NORMAL",
                status="HANDOFF_PENDING",
                version=3,
                cycle_no=2,
                requested_mode="HUMAN",
                resolution_mode=None,
                issue_tags=[],
                sla_due_at="2026-11-04T03:00:00.000000Z",
                first_replied_at=None,
                resolved_at=None,
                is_complaint=False,
                primary_issue=None,
                label_status="UNLABELED",
                human_verified=False,
            )
        ],
        "audit_events": [
            dict(
                event_id=event,
                ticket_id=ticket,
                cycle_no=2,
                actor_user_id=admin,
                actor_service="backend-a",
                action="TICKET_REOPENED",
                target_type="TICKET",
                target_id=ticket,
                event_key=uid("event-key"),
                payload={},
                result="SUCCESS",
                reason_code="CUSTOMER_REOPENED",
            )
        ],
        "followup_actions": [
            dict(
                action_id=action,
                ticket_id=ticket,
                product_id=None,
                cycle_no=1,
                responsibility_cycle_no=2,
                origin_team_id=team,
                owner_team_id=team,
                owner_user_id=admin,
                kind="CHECK_STATUS",
                status="OPEN",
                blocks_resolution=True,
                due_at="2026-11-05T03:00:00.000000Z",
                completed_at=None,
                cancelled_at=None,
                cancellation_reason=None,
                version=2,
            )
        ],
    }
    for records in rows.values():
        for r in records:
            r.update(created_at=T, data_origin="SYNTHETIC")
    for table, records in rows.items():
        if table != "audit_events":
            for r in records:
                r["updated_at"] = T
    files = [jsonl("db-projections/" + table + ".jsonl", records) for table, records in rows.items()]
    save(
        "db-projections/manifest.json",
        {
            "contract_status": "SYNTHETIC_ALLOWLIST_DB_PROJECTIONS_NOT_FULL_ROWS",
            "source": "NO_DATABASE_READ_GENERATED_EXAMPLES",
            "migration_head": "0006",
            "files": files,
            "omitted_sensitive_columns": [
                "users.login_name",
                "users.password_hash",
                "customers.display_name",
                "customers.profile_masked",
                "customers.customer_key",
                "orders.order_number",
                "followup_actions.public_note",
                "followup_actions.internal_note",
            ],
        },
    )

    # Public fixed example key. Not an application key and never used against real data.
    key = bytes(range(32))
    domain = "org-demo-authorized-silver"
    key_version = "demo-public-v1"

    def pseudonym(kind, value):
        return (
            None
            if value is None
            else hmac.new(
                key, f"csflow|{kind}|v1|{domain}|{value}".encode("utf-8"), hashlib.sha256
            ).hexdigest()
        )

    projection = {
        "products": {"product_id", "sku", "category", "active", "created_at", "updated_at"},
        "customers": {"customer_id", "deleted_at"},
        "orders": {
            "order_id",
            "customer_id",
            "product_id",
            "quantity",
            "order_status",
            "payment_status",
            "amount",
            "placed_at",
            "paid_at",
            "version",
        },
        "tickets": {
            "ticket_id",
            "customer_id",
            "order_id",
            "product_id",
            "team_id",
            "status",
            "version",
            "cycle_no",
            "requested_mode",
            "resolution_mode",
            "category",
            "is_complaint",
            "primary_issue",
            "label_status",
            "first_replied_at",
            "resolved_at",
            "created_at",
            "updated_at",
        },
        "followup_actions": {
            "action_id",
            "ticket_id",
            "product_id",
            "cycle_no",
            "responsibility_cycle_no",
            "origin_team_id",
            "owner_team_id",
            "status",
            "blocks_resolution",
            "due_at",
            "completed_at",
            "cancelled_at",
            "cancellation_reason",
            "version",
            "created_at",
            "updated_at",
        },
    }
    identity = {
        "customer_id": ("customer_ref", "customer"),
        "order_id": ("order_ref", "order"),
        "ticket_id": ("ticket_ref", "ticket"),
        "action_id": ("action_ref", "followup"),
    }
    exported = {}
    for table, fields in projection.items():
        values = []
        for row in rows[table]:
            value = {}
            for field in fields:
                v = row[field]
                if field in identity:
                    target, kind = identity[field]
                    value[target] = pseudonym(kind, v)
                else:
                    value[field] = v
            values.append(value)
        exported[table] = sorted(values, key=lambda r: next(iter(sorted(r.items()))))
    files = [
        jsonl("export-proposal/" + table + "/part-00001.jsonl", records)
        for table, records in exported.items()
    ]
    save(
        "export-proposal/manifest.json",
        {
            "contract_status": "PROPOSED_NOT_IMPLEMENTED",
            "source_system": "csflow-docs-local-synthetic",
            "export_batch_id": uid("export-batch"),
            "export_schema_version": "proposed-silver-v1",
            "source_migration_head": "0006",
            "data_origin": "SYNTHETIC",
            "source_as_of": "2026-11-03T03:00:00.000000Z",
            "snapshot_consistency": "EXAMPLE_ONLY_NO_SNAPSHOT_WAS_EXPORTED",
            "extraction_started_at": "2026-11-03T03:00:00.000000Z",
            "extraction_completed_at": "2026-11-03T03:00:01.000000Z",
            "scope": {"type": "EXPLICIT_TEAM_SET", "team_ids": [team]},
            "join_domain": domain,
            "key_version": key_version,
            "format": {
                "encoding": "UTF-8",
                "bom": False,
                "line_ending": "LF",
                "final_lf": True,
                "compression": "none",
                "numeric": "fixed-scale-string",
                "timestamp": "UTC-six-fraction-Z",
            },
            "completeness": {
                "sales": "unknown",
                "complaints": "unknown",
                "episode_state": "unknown",
                "reason": "SMALL_EXAMPLE_NOT_A_COMPLETE_SOURCE",
            },
            "full_snapshot": True,
            "table_coverage": "EXAMPLE_FIVE_PROJECTIONS_ONLY_NOT_ALL_SILVER_INPUTS",
            "files": files,
        },
    )
    save(
        "export-proposal/hmac-vector.json",
        {
            "contract_status": "PROPOSED_NOT_IMPLEMENTED",
            "warning": "PUBLIC_SYNTHETIC_EXAMPLE_KEY_NEVER_USE_IN_DEPLOYMENT",
            "example_key_hex": key.hex(),
            "join_domain": domain,
            "key_version": key_version,
            "input_customer_uuid": customer,
            "input_utf8": f"csflow|customer|v1|{domain}|{customer}",
            "customer_ref": pseudonym("customer", customer),
        },
    )

    shutil.copyfile(ROOT / "docs/examples/analytics-batch.json", OUT / "publish-request.json")
    submission = Submission.model_validate_json((OUT / "publish-request.json").read_text())
    content = digest(canonical_submission(submission))
    bid = str(submission.manifest.batch_id)
    base = {
        "batch_id": bid,
        "content_hash": content,
        "is_current": False,
        "validation_passed": False,
        "validated_at": None,
        "published_at": None,
        "validation_result": {"passed": False, "codes": ["NOT_VALIDATED"]},
    }
    save("receive-response.json", dict(base, status="RECEIVED"))
    checked = dict(
        base,
        status="VALIDATED",
        validation_passed=True,
        validated_at="2026-11-03T03:01:00Z",
        validation_result={
            "passed": True,
            "codes": [],
            "validator_version": "analytics-v1",
            "origin_verified": False,
        },
    )
    save("validate-response.json", checked)
    save(
        "publish-response.json",
        dict(checked, status="SUCCEEDED", is_current=True, published_at="2026-11-03T03:02:00Z"),
    )
    save(
        "failed-validation-response.json",
        dict(
            base,
            status="FAILED",
            validated_at="2026-11-03T03:01:00Z",
            validation_result={
                "passed": False,
                "codes": ["PAYLOAD_CHECKSUM", "ROW_COUNT"],
                "validator_version": "analytics-v1",
                "origin_verified": False,
            },
        ),
    )
    save(
        "conflict-response.json", {"error": {"code": "BATCH_CONTENT_CONFLICT", "request_id": uid("request")}}
    )
    save(
        "unpublished-kpi-response.json",
        {
            "availability": "UNAVAILABLE",
            "reason": "NO_PUBLISHED_BATCH",
            "meta": None,
            "metrics": None,
            "definition": None,
            "quality": None,
            "coverage": None,
            "grain": None,
            "rows": [],
        },
    )
    save(
        "service-claims.json",
        {
            "sub": "PROPOSED_FABRIC_SUBJECT_NOT_CONFIGURED",
            "iss": "csflow-analytics-service",
            "aud": "csflow-analytics-ingest",
            "iat": 1793674800,
            "nbf": 1793674800,
            "exp": 1793675100,
            "permissions": ["analytics:receive", "analytics:publish"],
        },
    )
    save(
        "example-metadata.json",
        {
            "all_samples": "SYNTHETIC_DOCUMENTATION_ONLY",
            "api_responses": "Pydantic-validated examples, not live HTTP receipts",
            "gold_sample": "Independent supplied facts; NOT computed from tiny db-projections",
            "proposal_five_jsonl": "Five rows, unrelated to a claimed 12008-row delivery",
            "export_pipeline_implemented": False,
        },
    )
    print(
        "Generated synthetic projections, proposed five-file manifest and existing API examples; no DB/network access."
    )


if __name__ == "__main__":
    main()
