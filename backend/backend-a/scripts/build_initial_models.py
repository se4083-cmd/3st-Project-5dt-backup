"""One-time source adapter used to create the initial, reviewable model definitions.

Never run during application startup or migrations. The original contract is external.
"""

import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "reference/fixture"
contracts = [
    c for c in json.loads((source / "schema_contract.json").read_text(encoding="utf-8")) if c["primary_key"]
]
ddl = (source / "code/postgres_fixture_schema.sql").read_text(encoding="utf-8")
foreign = {}
for table, col, dest, key in re.findall(
    r"ALTER TABLE (\w+) ADD FOREIGN KEY \((\w+)\) REFERENCES (\w+)\((\w+)\)", ddl
):
    foreign[table, col] = f"{dest}.{key}"
types = {
    "uuid": "Uuid(as_uuid=False)",
    "text": "Text()",
    "bigint": "BigInteger()",
    "boolean": "Boolean()",
    "jsonb": "JSON().with_variant(JSONB(), 'postgresql')",
    "timestamptz": "UTCDateTime()",
    "date": "Date()",
    "double precision": "Float()",
}
defaults = {
    "created_at": "utcnow",
    "updated_at": "utcnow",
    "data_origin": "'APPLICATION'",
    "scenario_id": "'LIVE'",
    "generator_version": "'backend-a-v1'",
    "seed": "0",
}
special = {
    "tickets": {
        "category": "'UNCLASSIFIED'",
        "priority": "'NORMAL'",
        "status": "'OPEN'",
        "version": "1",
        "cycle_no": "1",
        "requested_mode": "'AUTO'",
        "issue_tags": "list",
        "is_complaint": "False",
        "label_status": "'UNLABELED'",
        "human_verified": "False",
    },
    "messages": {"final_reply": "False"},
    "audit_events": {"payload": "dict"},
    "automation_jobs": {"status": "'PENDING'", "attempt": "0", "next_attempt_at": "utcnow"},
}
text = '''"""Application tables mapped from the supplied fixture contract, with explicit app constraints.

This file is owned by Backend A; fixture SQL is never executed as a migration.
"""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, Float, ForeignKey,
    ForeignKeyConstraint, Index, Integer, JSON, MetaData, Numeric, String,
    Table, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from app.db import UTCDateTime, utcnow

metadata = MetaData(naming_convention={
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
})
'''
for c in contracts:
    n = c["table"]
    text += f"\n{n} = Table({n!r}, metadata,\n"
    for f in c["fields"]:
        name, typ = f["name"], f["postgres_type"]
        type_expr = "Numeric" + typ[len("numeric") :] if typ.startswith("numeric") else types[typ]
        args = [repr(name), type_expr]
        if (n, name) in foreign:
            args.append(f"ForeignKey({foreign[n, name]!r})")
        if name in c["primary_key"]:
            args.append("primary_key=True")
        required = n in ("tickets", "messages", "automation_jobs", "assignments") and name in (
            "ticket_id",
            "cycle_no",
        )
        args.append(f"nullable={f['nullable'] and not required}")
        default = special.get(n, {}).get(name, defaults.get(name))
        if default is not None:
            args.append(f"default={default}")
        text += "    Column(" + ", ".join(args) + "),\n"
    extras = {
        "analytics_batches": "    Column('validation_passed', Boolean(), nullable=False, server_default=text('false')),\n"
        "    Column('validated_at', UTCDateTime()),\n"
        "    Column('content_hash', String(64)),\n",
        "users": "    Column('is_dev_account', Boolean(), nullable=False, server_default=text('false')),\n",
        "tickets": "    Column('team_id', Uuid(as_uuid=False), ForeignKey('teams.team_id')),\n",
        "messages": "    Column('visibility', String(16), nullable=False, server_default='INTERNAL'),\n",
        "followup_actions": "    Column('origin_team_id', Uuid(as_uuid=False), ForeignKey('teams.team_id'), nullable=False, default=lambda c: c.get_current_parameters()['owner_team_id']),\n"
        "    Column('responsibility_cycle_no', BigInteger(), default=lambda c: c.get_current_parameters().get('cycle_no')),\n"
        "    Column('cancelled_at', UTCDateTime()),\n"
        "    Column('cancellation_reason', String(64)),\n",
        "automation_jobs": "    Column('expected_ticket_version', BigInteger(), nullable=False),\n"
        "    Column('lease_owner', String(128)),\n"
        "    Column('job_kind', String(16), nullable=False, server_default='AUTO'),\n"
        "    Column('source_message_id', Uuid(as_uuid=False), ForeignKey('messages.message_id')),\n"
        "    Column('reason_code', String(64)),\n"
        "    Column('automation_generation', BigInteger(), nullable=False, server_default=text('1')),\n",
        "audit_events": "    Column('result', String(16), nullable=False, server_default='SUCCESS'),\n"
        "    Column('reason_code', String(64), nullable=False, server_default='FIXTURE_HISTORY'),\n",
    }
    text += extras.get(n, "") + ")\n"
(root / "app/models.py").write_text(text, encoding="utf-8")
