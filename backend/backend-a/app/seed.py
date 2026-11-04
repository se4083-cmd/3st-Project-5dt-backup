"""Explicit synthetic seed commands. Never invoked by the API or startup script."""

import argparse
import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.auth import hash_password
from app.config import get_settings
from app.db import build_engine, session_factory, utcnow
from app.model_constraints import team_categories, user_team_scopes
from app.models import customers, orders, products, teams, users
from app.schema import metadata


def stable_id(label):
    return str(uuid5(NAMESPACE_URL, "csflow-backend-a-development/" + label))


def require_development(settings):
    if settings.app_env not in ("development", "test") or not settings.enable_dev_seed:
        raise ValueError("Seed requires development/test and explicit ENABLE_DEV_SEED=true")


def insert_missing(session, table, rows):
    """Insert missing keys only. Never update/delete existing application or fixture rows."""
    keys = [c.name for c in table.primary_key]
    existing = {tuple(row) for row in session.execute(select(*(table.c[k] for k in keys)))}
    pending = [r for r in rows if tuple(r[k] for k in keys) not in existing]
    for start in range(0, len(pending), 250):
        session.execute(table.insert(), pending[start : start + 250])
    return len(pending)


def seed_minimal(session, password):
    if not password or not 12 <= len(password) <= 128:
        raise ValueError("Set DEV_SEED_PASSWORD to a locally chosen 12–128 character password")
    now = utcnow()
    common = dict(
        created_at=now,
        updated_at=now,
        data_origin="SYNTHETIC",
        scenario_id="BACKEND_A_DEV",
        generator_version="backend-a-dev-v1",
        seed=20261102,
    )
    team_id = stable_id("team")
    insert_missing(
        session,
        teams,
        [dict(team_id=team_id, name="개발 배송팀", supported_categories=["DELIVERY"], active=True, **common)],
    )
    insert_missing(session, team_categories, [dict(team_id=team_id, category="DELIVERY")])
    password_hash = hash_password(password)
    for label, role in [
        ("customer1", "CUSTOMER"),
        ("customer2", "CUSTOMER"),
        ("agent", "AGENT"),
        ("admin", "ADMIN"),
    ]:
        user_id = stable_id(label)
        insert_missing(
            session,
            users,
            [
                dict(
                    user_id=user_id,
                    login_name=f"dev-{label}@example.test",
                    password_hash=password_hash,
                    role=role,
                    active=True,
                    team_id=team_id if role == "AGENT" else None,
                    allowed_team_ids=[team_id] if role != "CUSTOMER" else [],
                    is_dev_account=True,
                    **common,
                )
            ],
        )
        if role != "CUSTOMER":
            insert_missing(session, user_team_scopes, [dict(user_id=user_id, team_id=team_id)])
        else:
            customer_id = stable_id(label + "/profile")
            insert_missing(
                session,
                customers,
                [
                    dict(
                        customer_id=customer_id,
                        user_id=user_id,
                        display_name=f"개발 합성 {label}",
                        verification_status="VERIFIED",
                        customer_key=hashlib.sha256(("SYNTHETIC/" + label).encode()).hexdigest(),
                        **common,
                    )
                ],
            )
            product_id = stable_id("product")
            insert_missing(
                session,
                products,
                [
                    dict(
                        product_id=product_id,
                        sku="BACKEND-A-DEV-01",
                        name="개발 합성 상품",
                        category="생활용품",
                        active=True,
                        **common,
                    )
                ],
            )
            insert_missing(
                session,
                orders,
                [
                    dict(
                        order_id=stable_id(f"{label}/order/{i}"),
                        customer_id=customer_id,
                        product_id=product_id,
                        quantity=1,
                        order_number=f"BACKEND-A-{label}-{i}",
                        order_status="DELIVERED",
                        payment_status="PAID",
                        amount=10000,
                        placed_at=now,
                        paid_at=now,
                        version=1,
                        **common,
                    )
                    for i in range(3)
                ],
            )
    return {"accounts": [f"dev-{n}@example.test" for n in ("customer1", "customer2", "agent", "admin")]}


def seed_fixture(session, fixture_dir: Path):
    """Load all 22 official tables in FK dependency order, in the caller's ONE transaction.

    Silver/derived auxiliary files remain in the external source; no score calculation or publish occurs.
    """
    config = json.loads((fixture_dir / "config.json").read_text(encoding="utf-8-sig"))
    if config.get("data_origin") != "SYNTHETIC":
        raise ValueError("Only explicitly marked synthetic fixtures are accepted")
    contract = json.loads((fixture_dir / "schema_contract.json").read_text(encoding="utf-8-sig"))
    contract = {c["table"]: c for c in contract if c["primary_key"]}
    if set(contract) != set(metadata.tables) - {
        "user_team_scopes",
        "team_categories",
        "idempotency_keys",
        "analytics_receipts",
        "analytics_publication",
        "staff_permissions",
        "queue_routes",
        "automation_control",
        "automation_control_history",
        # P1 storage is outside the official P0 fixture contract.
        "p1_idempotency",
        "p1_tasks",
        "p1_ai_call_attempts",
    }:
        raise ValueError("Fixture official table set differs from the reviewed 22-table contract")
    data = {
        name: json.loads((fixture_dir / "data" / f"{name}.json").read_text(encoding="utf-8-sig"))
        for name in contract
    }
    ticket_versions = {t["ticket_id"]: t["version"] for t in data["tickets"]}
    routed_team = {
        a["ticket_id"]: a["team_id"] for a in sorted(data["assignments"], key=lambda a: a["assigned_at"])
    }
    counts = {}
    for table in metadata.sorted_tables:
        if table.name not in data:
            continue
        c = contract[table.name]
        fields = {f["name"] for f in c["fields"]}
        extra_fields = {
            "users": {"is_dev_account"},
            "tickets": {"team_id"},
            "messages": {"visibility"},
            "automation_jobs": {
                "expected_ticket_version",
                "lease_owner",
                "job_kind",
                "source_message_id",
                "reason_code",
                "automation_generation",
            },
            "audit_events": {"result", "reason_code"},
            "analytics_batches": {"validation_passed", "validated_at", "content_hash"},
            "followup_actions": {
                "origin_team_id",
                "responsibility_cycle_no",
                "cancelled_at",
                "cancellation_reason",
            },
        }
        if fields != set(table.c.keys()) - extra_fields.get(table.name, set()):
            raise ValueError(f"Fixture field set mismatch: {table.name}")
        rows = []
        for original in data[table.name]:
            r = dict(original)
            if r.get("data_origin") != "SYNTHETIC" or set(r) != fields:
                raise ValueError(f"Invalid synthetic row: {table.name}")
            for f in c["fields"]:
                value = r[f["name"]]
                if value is None and not f["nullable"]:
                    raise ValueError(f"Required fixture value: {table.name}.{f['name']}")
                if value is not None and f["postgres_type"] == "timestamptz":
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if value.tzinfo is None:
                        raise ValueError("Naive fixture time")
                elif value is not None and f["postgres_type"] == "date":
                    value = date.fromisoformat(value)
                r[f["name"]] = value
            if table.name == "tickets":
                r["team_id"] = routed_team.get(r["ticket_id"])
            elif table.name == "messages":
                known_public = (r["role"] == "CUSTOMER" and r["direction"] == "IN") or (
                    r["role"] in ("AGENT", "ASSISTANT")
                    and r["direction"] == "OUT"
                    and r["approval_id"] is not None
                )
                r["visibility"] = "PUBLIC" if known_public else "INTERNAL"
            elif table.name == "automation_jobs":
                r["expected_ticket_version"] = ticket_versions[r["ticket_id"]]
                r["lease_owner"] = None
            elif table.name == "analytics_batches" and (r["is_current"] or r["status"] != "VALIDATED"):
                raise ValueError("Fixture batch must remain VALIDATED and unpublished")
            rows.append(r)
        counts[table.name] = insert_missing(session, table, rows)
    scope_rows = [dict(user_id=u["user_id"], team_id=t) for u in data["users"] for t in u["allowed_team_ids"]]
    category_rows = [
        dict(team_id=t["team_id"], category=c) for t in data["teams"] for c in t["supported_categories"]
    ]
    insert_missing(session, user_team_scopes, scope_rows)
    insert_missing(session, team_categories, category_rows)
    return {"inserted": counts, "source_as_of": config["source_as_of"], "published": False}


def main():
    parser = argparse.ArgumentParser(description="Explicit development-only synthetic data import")
    parser.add_argument("mode", choices=["minimal", "fixture"])
    parser.add_argument("--fixture-dir", type=Path)
    args = parser.parse_args()
    settings = get_settings()
    require_development(settings)
    engine = build_engine(settings)
    try:
        with session_factory(engine).begin() as session:
            if args.mode == "minimal":
                result = seed_minimal(session, os.environ.get("DEV_SEED_PASSWORD"))
            else:
                if not args.fixture_dir:
                    parser.error("fixture mode requires --fixture-dir")
                result = seed_fixture(session, args.fixture_dir)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
