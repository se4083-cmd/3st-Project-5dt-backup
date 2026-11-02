"""Check actual OpenAPI and generate/verify offline canonical hash vectors."""

import argparse
import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.analytics_canonical import canonical_submission, digest, normalize, table_hashes
from app.analytics_schemas import Submission
from app.automation_control import ResumeCommand, StopCommand
from app.config import Settings
from app.followup_schemas import FollowupCreate, FollowupPatch, FollowupState
from app.main import create_app
from app.retention import RetentionRequest
from app.schemas import AgentRequest, ReopenRequest, TicketCreate
from app.staff_detail import DetailPurpose

ROOT = Path(__file__).resolve().parents[1]


def vectors():
    example = Submission.model_validate_json(
        (ROOT / "docs/examples/analytics-batch.json").read_text(encoding="utf-8")
    )
    canonical = canonical_submission(example)
    sample = {"z": Decimal("50.000000"), "at": datetime.fromisoformat("2026-10-31T12:00:00+09:00"), "a": 1.0}
    normalized = normalize(sample)
    # Show row sorting separately from generic object-key sorting.
    shuffled = example.model_copy(deep=True)
    row = shuffled.payload.analytics_daily[0].model_copy(deep=True)
    row.day = row.day - timedelta(days=1)
    shuffled.payload.analytics_daily.append(row)
    ordered = canonical_submission(shuffled)["payload"]["analytics_daily"]
    return {
        "canonical_version": "csflow-json-v1",
        "source": "LOCAL_SYNTHETIC_OFFLINE_EXAMPLE",
        "primitive_python_input": {
            "Decimal": "50.000000",
            "datetime": "2026-10-31T12:00:00+09:00",
            "float": 1.0,
        },
        "normalized_sample": normalized,
        "canonical_json": json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
        "sha256": digest(sample),
        "submission_file": "analytics-batch.json",
        "submission_content_sha256": digest(canonical),
        "payload_sha256": table_hashes(canonical["payload"]),
        "pk_sorted_daily_rows": ordered,
        "pk_sorted_daily_sha256": digest(ordered),
        "source_input_hashes": "File-byte hashes are a separate upstream claim; not these payload hashes",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-examples", action="store_true")
    args = parser.parse_args()
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret=secrets.token_urlsafe(48),
        )
    )
    try:
        actual = app.openapi()
    finally:
        app.state.engine.dispose()
    recorded = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    if actual != recorded:
        raise RuntimeError("OPENAPI_NEEDS_REGENERATION")
    schemas = actual["components"]["schemas"]
    public = set(schemas["FollowupPublic"]["properties"])
    if public & {"internal_note", "owner_user_id", "owner_team_id", "blocks_resolution", "revision"}:
        raise RuntimeError("PUBLIC_FOLLOWUP_CONTRACT_LEAK")
    if not {"revision", "cycle_no"} <= set(schemas["TicketPublic"]["properties"]):
        raise RuntimeError("TICKET_REVISION_CONTRACT_MISSING")
    service = actual["paths"]["/api/v1/analytics/batches"]["post"]
    if service["security"] != [{"AnalyticsServiceBearer": []}]:
        raise RuntimeError("SERVICE_AUTH_CONTRACT_MISMATCH")
    # These are shape examples; fixture assignment and permission preconditions
    # are described in the Frontend handoff, not bypassed by the examples.
    examples = json.loads((ROOT / "docs/examples/frontend-requests.json").read_text(encoding="utf-8"))
    models = {
        "TicketCreate": TicketCreate,
        "ReopenRequest": ReopenRequest,
        "AgentRequest": AgentRequest,
        "FollowupCreate": FollowupCreate,
        "FollowupPatch": FollowupPatch,
        "FollowupState": FollowupState,
        "DetailPurpose": DetailPurpose,
        "StopCommand": StopCommand,
        "ResumeCommand": ResumeCommand,
        "RetentionRequest": RetentionRequest,
    }
    for item in examples["requests"]:
        if item["path"] not in actual["paths"] or item["method"].lower() not in actual["paths"][item["path"]]:
            raise RuntimeError("EXAMPLE_ENDPOINT_MISSING")
        if item.get("model"):
            models[item["model"]].model_validate(item["body"])
    for name in ("TicketPublic", "TicketDetail", "MessagePublic"):
        if {"customer_ref", "current_proposals", "gate_results", "approvals"} & set(
            schemas[name]["properties"]
        ):
            raise RuntimeError("STAFF_DETAIL_IN_PUBLIC_SCHEMA")
    if schemas["StaffTicketDetail"].get("additionalProperties") is not False:
        raise RuntimeError("STAFF_DETAIL_ALLOWLIST_NOT_CLOSED")
    retention_paths = [p for p in actual["paths"] if "/retention" in p]
    if retention_paths != ["/api/v1/staff/retention/dry-run"] or set(actual["paths"][retention_paths[0]]) != {
        "post"
    }:
        raise RuntimeError("RETENTION_MUST_REMAIN_PREVIEW_ONLY")
    for name in ("RetentionRequest", "ReviewPolicy", "RetentionReport", "TargetReview"):
        if schemas[name].get("additionalProperties") is not False:
            raise RuntimeError("RETENTION_ALLOWLIST_NOT_CLOSED")
    target = ROOT / "docs/examples/canonical-hashes.json"
    result = vectors()
    if args.write_examples:
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    elif json.loads(target.read_text(encoding="utf-8")) != result:
        raise RuntimeError("HASH_EXAMPLES_OUT_OF_DATE")
    print(
        "PASS: actual OpenAPI, role request shapes, public DTO boundary and canonical hash vectors; no network/DB connection"
    )


if __name__ == "__main__":
    main()
