"""Documentation consistency checks, not an Export implementation or business test suite."""

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from app.analytics_canonical import canonical_submission, digest, table_hashes  # noqa: E402
from app.analytics_schemas import BatchStatus, KpiResponse, Submission  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.schema import metadata  # noqa: E402
from app.schemas import ErrorEnvelope  # noqa: E402

OUT = ROOT / "docs/fabric-data-contract"
SAMPLES = OUT / "samples"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data
    assert not data or data.endswith(b"\n")
    return [json.loads(line) for line in data.decode("utf-8").splitlines()]


def typed(value, field):
    if value is None:
        assert field["nullable"], field["column_name"]
        return None
    kind = field["pg_type"]
    if kind == "uuid":
        assert isinstance(value, str) and str(UUID(value)) == value
    elif kind == "timestamp with time zone":
        assert isinstance(value, str) and re.fullmatch(r".*\.\d{6}Z", value)
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert value.utcoffset().total_seconds() == 0
    elif kind == "date":
        value = date.fromisoformat(value)
    elif kind.startswith("numeric"):
        assert isinstance(value, str)
        value = Decimal(value)
        assert value.is_finite()
        scale = int(kind.split(",")[1].strip(" )"))
        assert value.as_tuple().exponent == -scale
    elif kind in ("integer", "bigint"):
        assert type(value) is int
    elif kind == "boolean":
        assert type(value) is bool
    elif kind == "jsonb":
        assert isinstance(value, (dict, list))
    else:
        assert isinstance(value, str)
    return value


def check_files(manifest):
    for f in manifest["files"]:
        p = SAMPLES / f["object_key"]
        assert p.resolve().is_relative_to(SAMPLES.resolve())
        data = p.read_bytes()
        assert hashlib.sha256(data).hexdigest() == f["sha256"]
        assert len(data) == f["byte_count"] and len(rows(p)) == f["row_count"]


def verify_database(url, raw_rows, submission):
    """Only a new extractor-owned loopback DB; all synthetic inserts rolled back."""
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.analytics_validation import validate_submission
    from app.local_guard import require_local_database

    parsed = require_local_database(url, postgres_only=True)
    assert parsed.host == "127.0.0.1" and parsed.username == "schema_docs" and parsed.database == "postgres"
    engine = create_engine(url, hide_parameters=True, echo=False)
    catalog = load(OUT / "schema-catalog.json")
    by_column = {(c["table_name"], c["column_name"]): c for c in catalog["columns"]}
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                for name in [
                    "teams",
                    "users",
                    "customers",
                    "products",
                    "orders",
                    "tickets",
                    "audit_events",
                    "followup_actions",
                ]:
                    for raw in raw_rows[name]:
                        row = {k: typed(v, by_column[(name, k)]) for k, v in raw.items()}
                        if name == "users":
                            row.update(
                                login_name="disabled-" + row["user_id"] + "@example.invalid",
                                password_hash="!DISABLED_SYNTHETIC_LOGIN",
                                is_dev_account=True,
                            )
                        if name == "customers":
                            row.update(
                                display_name="문서 전용 합성",
                                verification_status="VERIFIED",
                                customer_key="SYNTHETIC_NOT_HMAC_" + row["customer_id"],
                            )
                        if name == "orders":
                            row["order_number"] = "DOC-ONLY-" + row["order_id"]
                        connection.execute(metadata.tables[name].insert().values(**row))
                # Gold example is independent of the tiny source projections.
                team = str(submission.manifest.team_ids[0])
                product = str(submission.manifest.product_ids[0])
                connection.execute(
                    metadata.tables["teams"]
                    .insert()
                    .values(
                        team_id=team, name="문서 Gold 합성 팀", supported_categories=["PRODUCT"], active=True
                    )
                )
                connection.execute(
                    metadata.tables["products"]
                    .insert()
                    .values(
                        product_id=product,
                        sku="SYNTHETIC-DOC-GOLD",
                        name="문서 Gold 합성 상품",
                        category="생활용품",
                        active=True,
                    )
                )
                with Session(bind=connection) as session:
                    result = validate_submission(session, submission)
                    assert result["passed"], result["codes"]
            finally:
                transaction.rollback()
            assert connection.scalar(select(func.count()).select_from(metadata.tables["tickets"])) == 0
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-database",
        action="store_true",
        help="For extract_local_schema child only; allowlisted URL from isolated environment.",
    )
    args = parser.parse_args()
    catalog = load(OUT / "schema-catalog.json")
    fields = {(c["table_name"], c["column_name"]): c for c in catalog["columns"]}
    raw = {p.stem: rows(p) for p in (SAMPLES / "db-projections").glob("*.jsonl")}
    for table, records in raw.items():
        for row in records:
            assert all((table, k) in fields for k in row)
            for k, v in row.items():
                typed(v, fields[(table, k)])
    for fk in (c for c in catalog["constraints"] if c["kind"] == "f"):
        for row in raw.get(fk["table_name"], []):
            if not all(k in row for k in fk["columns"]):
                continue
            values = tuple(row[k] for k in fk["columns"])
            if None in values:
                continue
            assert any(
                tuple(r[k] for k in fk["referenced_columns"]) == values
                for r in raw.get(fk["referenced_table"], [])
            ), fk["name"]
    for unique in (c for c in catalog["constraints"] if c["kind"] in ("p", "u")):
        records = [r for r in raw.get(unique["table_name"], []) if all(k in r for k in unique["columns"])]
        values = [
            tuple(r[k] for k in unique["columns"])
            for r in records
            if all(r[k] is not None for k in unique["columns"])
        ]
        assert len(values) == len(set(values))
    check_files(load(SAMPLES / "db-projections/manifest.json"))
    manifest = load(SAMPLES / "export-proposal/manifest.json")
    assert manifest["contract_status"] == "PROPOSED_NOT_IMPLEMENTED"
    check_files(manifest)
    vector = load(SAMPLES / "export-proposal/hmac-vector.json")
    assert (
        hmac.new(
            bytes.fromhex(vector["example_key_hex"]), vector["input_utf8"].encode(), hashlib.sha256
        ).hexdigest()
        == vector["customer_ref"]
    )
    exported = {p.parent.name: rows(p) for p in (SAMPLES / "export-proposal").glob("*/part-*.jsonl")}
    assert len(exported) == 5 and sum(len(x) for x in exported.values()) == 5
    customers = {r["customer_ref"] for r in exported["customers"]}
    orders = {r["order_ref"] for r in exported["orders"]}
    tickets = {r["ticket_ref"] for r in exported["tickets"]}
    products = {r["product_id"] for r in exported["products"]}
    for table, records in exported.items():
        original_keys = set(raw[table][0])
        identity = {
            "customer_ref": "customer_id",
            "order_ref": "order_id",
            "ticket_ref": "ticket_id",
            "action_ref": "action_id",
        }
        for row in records:
            for k, v in row.items():
                assert identity.get(k, k) in original_keys
                if k.endswith("_ref"):
                    assert v is None or re.fullmatch("[a-f0-9]{64}", v)
                else:
                    typed(v, fields[(table, k)])
            if "customer_ref" in row:
                assert row["customer_ref"] in customers
            if "order_ref" in row and table != "orders":
                assert row["order_ref"] is None or row["order_ref"] in orders
            if "ticket_ref" in row and table != "tickets":
                assert row["ticket_ref"] is None or row["ticket_ref"] in tickets
            if "product_id" in row:
                assert row["product_id"] is None or row["product_id"] in products
    forbidden = {
        "body",
        "draft",
        "internal_note",
        "public_note",
        "password_hash",
        "login_name",
        "email",
        "profile_masked",
        "customer_key",
        "lease_token",
        "access_token",
        "connection_string",
    }

    def reject_fields(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for v in value.values():
                reject_fields(v)
        if isinstance(value, list):
            for v in value:
                reject_fields(v)

    reject_fields(raw)
    reject_fields(exported)
    submission = Submission.model_validate(load(SAMPLES / "publish-request.json"))
    value = canonical_submission(submission)
    assert table_hashes(value["payload"]) == value["manifest"]["payload_checksums"]
    assert {t: len(v) for t, v in value["payload"].items()} == value["manifest"]["row_counts"]
    for name in ["receive", "validate", "publish", "failed-validation"]:
        response = BatchStatus.model_validate(load(SAMPLES / (name + "-response.json")))
        assert response.content_hash == digest(value)
    ErrorEnvelope.model_validate(load(SAMPLES / "conflict-response.json"))
    KpiResponse.model_validate(load(SAMPLES / "unpublished-kpi-response.json"))
    excerpt = load(OUT / "openapi-analytics.json")
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret=secrets.token_urlsafe(48),
        )
    )
    actual = app.openapi()
    app.state.engine.dispose()
    assert excerpt["info"] == actual["info"]
    for p, definition in excerpt["paths"].items():
        assert definition == actual["paths"][p]
    for name, definition in excerpt["components"]["schemas"].items():
        assert definition == actual["components"]["schemas"][name]
    assert "/internal/analytics/publish" not in actual["paths"]
    assert not catalog["native_enums"]
    assert set(metadata.tables) == {c["table_name"] for c in catalog["columns"]} - {"alembic_version"}
    if args.local_database:
        verify_database(os.environ["DATABASE_URL"], raw, submission)
    report = {
        "result": "PASS",
        "db_projection_tables": len(raw),
        "synthetic_projection_rows": sum(map(len, raw.values())),
        "proposed_export_files": 5,
        "proposed_export_rows": 5,
        "jsonl_bytes_counts_sha256": "PASS",
        "projection_types_fk_pk": "PASS",
        "hmac_public_vector": "PASS",
        "api_schema_canonical_hashes": "PASS",
        "actual_generated_openapi_paths": len(excerpt["paths"]),
        "postgresql_sample_constraints_and_semantic_gold_validation": "PASS"
        if args.local_database
        else "NOT_RUN_OFFLINE_ONLY",
        "azure_accessed": False,
        "live_http_executed": False,
        "actual_fabric_executed": False,
        "full_business_test_suite_executed": False,
    }
    (
        OUT / ("sample-postgres-verification.json" if args.local_database else "sample-verification.json")
    ).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
