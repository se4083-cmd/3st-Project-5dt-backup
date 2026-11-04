"""Extend documentation fixtures only. No DB, environment, network or application imports."""

import hashlib
import hmac
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

CONTRACT = Path(__file__).resolve().parents[1]
SAMPLES = CONTRACT / "samples"
PROPOSAL = SAMPLES / "export-proposal"
TABLES = ("products", "customers", "orders", "tickets", "followup_actions", "audit_events")
REASONS = {
    "TICKET_CREATED": ["CUSTOMER_SUBMITTED"],
    "TICKET_REOPENED": ["CUSTOMER_REOPENED", "HUMAN_CONTINUATION"],
    "AGENT_REQUESTED": ["CUSTOMER_REQUEST", "DISSATISFIED", "COMPLEX_ISSUE", "OTHER"],
    "AUTOMATIC_REPLY_COMMITTED": ["FENCED_COMMIT"],
}
ALIASES = {
    "customer_ref": ("customer_id", "customer"),
    "order_ref": ("order_id", "order"),
    "ticket_ref": ("ticket_id", "ticket"),
    "action_ref": ("action_id", "followup"),
    "event_ref": ("event_id", "event"),
}
PK = dict(products="product_id", customers="customer_ref", orders="order_ref",
          tickets="ticket_ref", followup_actions="action_ref", audit_events="event_ref")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main():
    manifest_path = PROPOSAL / "manifest.json"
    manifest = load(manifest_path)
    domain = manifest["join_domain"]
    vector = load(PROPOSAL / "hmac-vector.json")
    # Deliberately PUBLIC synthetic bytes, never an application credential.
    key = bytes.fromhex(vector["example_key_hex"])
    source = json.loads((SAMPLES / "db-projections/audit_events.jsonl").read_text("utf-8"))
    row = {name: source[name] for name in ("cycle_no", "action", "result", "reason_code", "created_at")}
    for target in ("event_ref", "ticket_ref"):
        column, kind = ALIASES[target]
        row[target] = hmac.new(key, f"csflow|{kind}|v1|{domain}|{source[column]}".encode(), hashlib.sha256).hexdigest()
    assert row["result"] == "SUCCESS" and row["reason_code"] in REASONS[row["action"]]
    path = PROPOSAL / "audit_events/part-00001.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())

    manifest.update(
        export_batch_id=str(uuid5(NAMESPACE_URL, "csflow-documentation-only/export-batch-with-audit-v1")),
        export_schema_version="proposed-silver-v1-audit-v1",
        table_coverage="EXAMPLE_SIX_PROJECTIONS_FIVE_CORE_PLUS_CUSTOMER_REFERENCE",
        fixture_basis="HISTORICAL_0006_SYNTHETIC_ROWS_NOT_A_CURRENT_DATABASE_SNAPSHOT",
        audit_source_review={"version": "0.11.0", "migration_file_head": "0011",
                             "git_head": "2af74b73eacb9e692e17b1ad166d35152085859d",
                             "database_checked": False},
        silver_approval="NOT_APPROVED",
    )
    manifest["files"] = []
    for table in TABLES:
        part = PROPOSAL / table / "part-00001.jsonl"
        raw = part.read_bytes()
        manifest["files"].append(dict(object_key=part.relative_to(SAMPLES).as_posix(),
                                      row_count=len(raw.splitlines()), byte_count=len(raw),
                                      sha256=hashlib.sha256(raw).hexdigest()))
    save(manifest_path, manifest)

    catalog = load(CONTRACT / "schema-catalog.json")
    columns = {(r["table_name"], r["column_name"]): r for r in catalog["columns"]}
    schema = dict(
        contract_status="PROPOSED_NOT_IMPLEMENTED", data_origin="SYNTHETIC",
        export_schema_version=manifest["export_schema_version"],
        purpose="EXPORT_PROJECTION_NOT_PHYSICAL_DB_OR_GOLD_SCHEMA",
        historical_fixture_migration_head="0006", audit_source_review=manifest["audit_source_review"],
        unknown_fields="REJECT", all_fields_required=True,
        audit_selection={"target_type": "TICKET", "result": ["SUCCESS"],
                         "reason_codes_by_action": REASONS,
                         "ticket_rule": "NON_NULL_AND_IN_EXPORTED_ALLOWED_TICKETS",
                         "cycle_rule": "PRESERVE_SOURCE_NULL_NO_CURRENT_CYCLE_FILL",
                         "payload": "EXCLUDED_ENTIRELY", "created_at": "AUDIT_RECORD_TIME_NOT_CONTACT_TIME"},
        tables=[],
    )
    fk_map = {"customer_ref": ("customers", "customer_ref"), "order_ref": ("orders", "order_ref"),
              "ticket_ref": ("tickets", "ticket_ref"), "product_id": ("products", "product_id")}
    for table in TABLES:
        sample = json.loads((PROPOSAL / table / "part-00001.jsonl").read_text("utf-8"))
        fields, fks = [], []
        for name in sorted(sample):
            column = ALIASES.get(name, (name, None))[0]
            physical = columns[table, column]
            pg_type = physical["pg_type"]
            wire = ("hmac_sha256_hex" if name in ALIASES else
                    "uuid" if pg_type == "uuid" else
                    "utc_timestamp_6" if pg_type == "timestamp with time zone" else
                    "integer" if pg_type in ("bigint", "integer") else
                    "boolean" if pg_type == "boolean" else
                    "decimal_2_string" if pg_type.startswith("numeric") else "string")
            nullable = physical["nullable"]
            if table == "audit_events" and name == "ticket_ref":
                nullable = False  # Selection filters NULL, not a source NOT NULL claim.
            fields.append(dict(name=name, source_column=column, source_pg_type=pg_type,
                               source_nullable=physical["nullable"], nullable=nullable, wire_type=wire))
            if name in fk_map and table != fk_map[name][0]:
                target, target_column = fk_map[name]
                fks.append(dict(column=name, table=target, target_column=target_column))
        schema["tables"].append(dict(table=table, primary_key=[PK[table]], fields=fields,
                                      foreign_keys=fks, fixture_rows=1))
    save(PROPOSAL / "schema_contract.json", schema)
    print("Documentation proposal: 6 files / 6 rows; no database or network access.")


if __name__ == "__main__":
    main()
