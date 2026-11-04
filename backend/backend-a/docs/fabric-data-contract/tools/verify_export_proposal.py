"""Offline documentation checks. Never imports the app, reads secrets, connects or extracts ZIPs."""

import argparse
import ast
import hashlib
import hmac
import json
import re
import zipfile
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from build_audit_proposal import ALIASES, PK, REASONS, TABLES

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
PROPOSAL = SAMPLES / "export-proposal"
BASELINES = {
    "products": "0ddafc3375ef7336f67dbbd4d20146822fead500970f2333258a850a842c2c91",
    "customers": "1db721166ab37ac36c66b751fd5e02041e5ff068e0a56fba106d63fff259aaed",
    "orders": "699490503bc365270607cebaace3d7217f43160268ed44e9f2ac1046c3d43884",
    "tickets": "80f5b90afffce6aba9e8cb82974e79f574f5a7f14ddda97a626fc745ad6030ba",
    "followup_actions": "d2e09334ef0d62970fb1f34b803ec437ede987519332b456f04e8b0a41a98a55",
}


def require(condition, label):
    if not condition:
        raise ValueError(label)  # Only fixed labels, never row values or credential contents.


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def parse(raw):
    def reject_constant(_):
        raise ValueError("Non-finite JSON number")
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return parse(path.read_bytes())


def rows(raw):
    values = [parse(line) for line in raw.decode("utf-8").splitlines()]
    require(all(isinstance(row, dict) for row in values), "JSONL object rows")
    return values


def stamp(value, six=False):
    require(isinstance(value, str), "Timestamp type")
    if six:
        require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value), "UTC six-fraction wire")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.utcoffset() is not None, "Aware timestamp")


def check_type(value, field):
    if value is None:
        require(field["nullable"], "NULL in required field: " + field["name"])
        return
    kind = field["wire_type"]
    if kind == "integer":
        require(type(value) is int and -(2**63) <= value < 2**63, "64-bit integer")
    elif kind == "boolean":
        require(type(value) is bool, "Boolean")
    else:
        require(type(value) is str, "String field")
        if kind == "uuid":
            require(str(UUID(value)) == value, "Canonical UUID")
        elif kind == "hmac_sha256_hex":
            require(re.fullmatch("[0-9a-f]{64}", value), "HMAC format")
        elif kind == "utc_timestamp_6":
            stamp(value, six=True)
        elif kind == "decimal_2_string":
            require(re.fullmatch(r"-?\d+\.\d{2}", value), "Fixed scale numeric")
        else:
            require(kind == "string", "Known wire type")


def foreign_key(data, table, column, target, target_column):
    allowed = {row[target_column] for row in data[target]}
    checked = sum(row.get(column) is not None for row in data[table])
    require(all(row.get(column) is None or row[column] in allowed for row in data[table]),
            "FK: " + table + "." + column)
    return dict(table=table, column=column, target=target + "." + target_column, non_null_checked=checked)


def verify_proposal(check_source=True):
    manifest = load(PROPOSAL / "manifest.json")
    schema = load(PROPOSAL / "schema_contract.json")
    require(manifest["contract_status"] == schema["contract_status"] == "PROPOSED_NOT_IMPLEMENTED", "Proposal status")
    require(manifest["export_schema_version"] == schema["export_schema_version"], "Schema version")
    require(manifest["data_origin"] == "SYNTHETIC" and manifest["silver_approval"] == "NOT_APPROVED", "Synthetic only")
    require(all(manifest["completeness"][k] == "unknown" for k in ("sales", "complaints", "episode_state")), "No invented completeness")
    expected = {"export-proposal/" + table + "/part-00001.jsonl" for table in TABLES}
    require({f["object_key"] for f in manifest["files"]} == expected and len(manifest["files"]) == 6, "Manifest inventory")
    require({t["table"] for t in schema["tables"]} == set(TABLES), "Schema table inventory")
    require({p.relative_to(SAMPLES).as_posix() for p in PROPOSAL.rglob("*.jsonl")} == expected, "No unlisted JSONL")
    vector = load(PROPOSAL / "hmac-vector.json")
    key = bytes.fromhex(vector["example_key_hex"])
    require(key == bytes(range(32)) and "PUBLIC_SYNTHETIC" in vector["warning"], "Public example key only")
    require(hmac.new(key, vector["input_utf8"].encode(), hashlib.sha256).hexdigest() == vector["customer_ref"], "HMAC vector")
    data, files, fks = {}, [], []
    for spec in schema["tables"]:
        table = spec["table"]
        name = "export-proposal/" + table + "/part-00001.jsonl"
        raw = (SAMPLES / name).read_bytes()
        require(not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw and raw.endswith(b"\n"), "UTF8 LF final-LF")
        data[table] = records = rows(raw)
        entry = dict(object_key=name, row_count=len(records), byte_count=len(raw), sha256=sha(raw))
        require(entry == next(f for f in manifest["files"] if f["object_key"] == name), "Manifest exact bytes/count/hash: " + table)
        if table in BASELINES:
            require(sha(raw) == BASELINES[table], "Original projection preserved: " + table)
        fields = {f["name"]: f for f in spec["fields"]}
        require(spec["primary_key"] == [PK[table]], "Explicit PK")
        source_rows = (rows((SAMPLES / "db-projections" / (table + ".jsonl")).read_bytes())
                       if check_source else [None] * len(records))
        require(len(source_rows) == len(records) == 1, "Tiny fixture count")
        for record, source in zip(records, source_rows):
            require(set(record) == set(fields), "Exact allowlist: " + table)
            for name, field in fields.items():
                check_type(record[name], field)
                if not check_source:
                    continue
                if name in ALIASES:
                    column, kind = ALIASES[name]
                    value = source[column]
                    wanted = None if value is None else hmac.new(
                        key, f"csflow|{kind}|v1|{manifest['join_domain']}|{value}".encode(), hashlib.sha256).hexdigest()
                else:
                    wanted = source[name]
                require(record[name] == wanted, "Source projection equality: " + table + "." + name)
        require(len({r[PK[table]] for r in records}) == len(records), "PK unique: " + table)
        files.append(entry)
    for spec in schema["tables"]:
        for fk in spec["foreign_keys"]:
            fks.append(foreign_key(data, spec["table"], fk["column"], fk["table"], fk["target_column"]))
    teams = set(manifest["scope"]["team_ids"])
    for table in ("tickets", "followup_actions"):
        for row in data[table]:
            for col in ("team_id", "origin_team_id", "owner_team_id"):
                require(row.get(col) is None or row[col] in teams, "Manifest team scope membership")
    for event in data["audit_events"]:
        require(event["result"] == "SUCCESS" and event["reason_code"] in REASONS[event["action"]], "Audit action/reason allowlist")
    require(set(data["audit_events"][0]) == {"event_ref", "ticket_ref", "cycle_no", "action", "result", "reason_code", "created_at"}, "Audit privacy allowlist")
    # All proposal JSON documents must parse, including public synthetic HMAC metadata.
    for path in PROPOSAL.rglob("*.json"):
        load(path)
    return dict(status="PASS", scope="OFFLINE_SYNTHETIC_PROPOSAL_ONLY", files_checked=len(files),
                rows_checked=sum(len(v) for v in data.values()), files=files, foreign_keys=fks,
                original_four_and_customer_reference="BYTE_IDENTICAL_SHA256_BASELINES",
                hmac=("PUBLIC_SYNTHETIC_VECTOR_AND_ALL_ALIASED_IDS_CHECKED" if check_source else
                      "PUBLIC_SYNTHETIC_VECTOR_ONLY_SOURCE_ROWS_NOT_IN_DELIVERY"),
                excluded_audit_fields="ALL_EXCEPT_THE_SEVEN_DECLARED_FIELDS",
                not_checked=["DATABASE", "AZURE", "REAL_EXPORT", "SILVER_APPROVAL", "TEAMS_USERS_SOURCE_FK_FILES_NOT_INCLUDED"])


def verify_incoming(path):
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, "ZIP CRC")
        require(len(archive.namelist()) == len(set(archive.namelist())), "ZIP unique members")
        require("manifest.json" not in {Path(n).name for n in archive.namelist()}, "Expected original Manifest absent")
        schema = parse(archive.read("schema/schema_contract.json"))
        specs = {t["table"]: t for t in schema}
        names = sorted(n for n in archive.namelist() if n.endswith(".jsonl"))
        require(len(names) == 5, "Five incoming JSONL files")
        data, files = {}, []
        for name in names:
            table = Path(name).stem
            raw = archive.read(name)
            records = rows(raw)
            data[table] = records
            fields = {f["name"]: f for f in specs[table]["fields"]}
            for row in records:
                require(set(row) == set(fields), "Incoming exact schema keys: " + table)
                for col, field in fields.items():
                    value = row[col]
                    require(value is not None or field["nullable"], "Incoming required field: " + table + "." + col)
                    if value is None:
                        continue
                    pg = field["postgres_type"]
                    if pg == "uuid":
                        UUID(value)
                    elif pg == "timestamptz":
                        stamp(value)
                    elif pg in ("bigint", "integer"):
                        require(type(value) is int, "Incoming integer")
                    elif pg == "boolean":
                        require(type(value) is bool, "Incoming boolean")
                    elif field.get("nested_json_encoded"):
                        require(isinstance(value, str), "Incoming encoded JSON string")
                        parse(value)
                    elif pg.startswith("numeric"):
                        require(not isinstance(value, bool) and Decimal(str(value)).is_finite(), "Incoming finite numeric")
                    elif pg in ("text", "varchar") or pg.startswith("varchar("):
                        require(isinstance(value, str), "Incoming text")
            pk = specs[table]["primary_key"]
            pk = [pk] if isinstance(pk, str) else pk
            require(len({tuple(r[c] for c in pk) for r in records}) == len(records), "Incoming PK unique: " + table)
            require(specs[table]["rows"] == len(records), "Incoming declared rows")
            files.append(dict(file=name, row_count=len(records), byte_count=len(raw), sha256=sha(raw)))
        fks = []
        for table, col, target, key in (
            ("orders", "product_id", "products", "product_id"),
            ("tickets", "order_id", "orders", "order_id"),
            ("tickets", "product_id", "products", "product_id"),
            ("followup_actions", "ticket_id", "tickets", "ticket_id"),
            ("followup_actions", "product_id", "products", "product_id"),
            ("audit_events", "ticket_id", "tickets", "ticket_id"),
        ):
            fks.append(foreign_key(data, table, col, target, key))
        order_products = {r["order_id"]: r["product_id"] for r in data["orders"]}
        require(all(r["order_id"] is None or order_products[r["order_id"]] == r["product_id"] for r in data["tickets"]), "Incoming ticket/order product agreement")
        order_customers = {r["order_id"]: r["customer_id"] for r in data["orders"]}
        require(all(r["order_id"] is None or order_customers[r["order_id"]] == r["customer_id"] for r in data["tickets"]), "Incoming ticket/order customer agreement")
        audits = data["audit_events"]
        require(len({r["event_key"] for r in audits}) == len(audits), "Incoming event_key unique")
        action_counts = dict(sorted(Counter(r["action"] for r in audits).items()))
        require(action_counts == {"CREATED": 1000, "CUSTOMER_CONTACT": 3000, "STATUS_CHANGED": 4820}, "Incoming audit action counts")
        require(all(r["target_type"] == "TICKET" and r["target_id"] == r["ticket_id"] for r in audits), "Incoming audit TICKET target FK")
        validations = [n for n in archive.namelist() if n.startswith("manifest/validation_")]
        require(len(validations) == 1, "One validation result")
        validation = parse(archive.read(validations[0]))
        for f in validation["files"]:
            raw = (SAMPLES / f["object_key"]).read_bytes()
            require(sha(raw) == f["actual_sha256"] and len(raw) == f["actual_byte_count"] and len(rows(raw)) == f["actual_row_count"] == 1, "Validation describes original one-row proposal")
        return dict(status="PASS_WITH_SEMANTIC_GAPS", archive_sha256=sha(path.read_bytes()),
                    original_manifest="ABSENT_NOT_RECONSTRUCTED_FROM_VALIDATION", files=files,
                    total_rows=sum(len(r) for r in data.values()), foreign_keys=fks,
                    audit_action_counts=action_counts, audit_payload_wire="JSON_ENCODED_STRING_ALL_8820",
                    audit_payload_keys_by_action={a: sorted({k for r in audits if r["action"] == a for k in parse(r["payload"])}) for a in action_counts},
                    a_model_fields_absent_from_incoming_audit=["result", "reason_code"],
                    audit_cycle_counts=dict(Counter(str(r["cycle_no"]) for r in audits)),
                    validation_result_scope=dict(files_checked=validation["files_checked"], verified_table_counts=validation["verified_table_counts"],
                                                 matches="ORIGINAL_A_ONE_ROW_FOUR_FILES_NOT_INCOMING_FULL_DATA",
                                                 silver_gate=validation["silver_gate"], gate_reasons=validation["gate_reasons"]),
                    not_checked=["CUSTOMER_USER_TEAM_MESSAGE_FK_NO_SOURCE_FILES", "ORIGINAL_MANIFEST_INTEGRITY_ABSENT", "ACTUAL_DATABASE", "FABRIC_SILVER_ACCEPTANCE", "REAL_CONTACT_EVENT_PRODUCER"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--incoming-zip", type=Path)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--delivery-only", action="store_true", help="No raw fixtures/app sources in delivery ZIP")
    args = parser.parse_args()
    report = verify_proposal(check_source=not args.delivery_only)
    # Hash only reviewed code, never load configuration or connect to an application/DB.
    backend = ROOT.parents[1]
    if not args.delivery_only:
        tree = ast.parse((backend / "app/models.py").read_text("utf-8"))
        audit = next(n.value for n in tree.body if isinstance(n, ast.Assign) and
                     any(isinstance(t, ast.Name) and t.id == "audit_events" for t in n.targets))
        current = {c.args[0].value: next((k.value.value for k in c.keywords if k.arg == "nullable"), True)
                   for c in audit.args if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "Column"}
        catalog = load(ROOT / "schema-catalog.json")
        historical = {r["column_name"]: r["nullable"] for r in catalog["columns"] if r["table_name"] == "audit_events"}
        require(len(current) == 17 and current == historical, "Current audit column names/NULL still match historical catalog")
        report["audit_source_column_and_null_comparison"] = "17_CURRENT_MODEL_COLUMNS_MATCH_HISTORICAL_CATALOG"
    report["reviewed_source_sha256"] = {} if args.delivery_only else {name: sha((backend / name).read_bytes()) for name in (
        "app/models.py", "app/model_constraints.py", "app/audit.py", "app/services.py",
        "app/ticket_commands.py", "app/finalization.py", "app/seed.py", "pyproject.toml")}
    if args.write_report:
        (ROOT / "audit-export-verification.json").write_bytes((json.dumps(report, indent=2) + "\n").encode())
    if args.incoming_zip:
        incoming = verify_incoming(args.incoming_zip)
        if args.write_report:
            (ROOT / "incoming-audit-review.json").write_bytes((json.dumps(incoming, indent=2) + "\n").encode())
        print("Incoming ZIP: 5 JSONL / 12008 rows / audit 8820; semantic gaps retained, no Silver approval.")
    print("PASS: proposal 6 JSONL / 6 rows; exact manifest, types, PK, available FK and HMAC; original five unchanged.")


if __name__ == "__main__":
    main()
