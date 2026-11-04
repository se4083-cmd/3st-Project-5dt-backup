"""Idempotent small SYNTHETIC team-dev seed, only in the dedicated Azure A DB.

No model/worker/Fabric is run. Original development/fixture accounts stay
production-ineligible. Separate cloud demo identities use freshly supplied
passwords and explicit narrow capabilities. Never invoked on API startup.
"""

import secrets

from sqlalchemy import select

from app import audit
from app.auth import hash_password
from app.automation_control import StopCommand, change
from app.model_constraints import user_team_scopes
from app.models import customers, orders, users
from app.seed import insert_missing, seed_minimal, stable_id
from app.staff_models import automation_control, staff_permissions


def cloud_id(label):
    return stable_id("azure-team-dev/" + label)


def seed_cloud(session, passwords):
    # Only generated local-style demo seed, NOT the 821-account external fixture.
    seed_minimal(session, secrets.token_urlsafe(40))
    for label in ("customer1", "customer2", "agent", "admin"):
        source = dict(
            session.execute(select(users).where(users.c.user_id == stable_id(label))).mappings().one()
        )
        source.update(
            user_id=cloud_id(label),
            login_name=f"demo-{label}@csflow.example.test",
            password_hash=hash_password(passwords[label]),
            is_dev_account=False,
            scenario_id="AZURE_TEAM_DEV_SYNTHETIC",
        )
        insert_missing(session, users, [source])
        if label in {"admin", "agent"}:
            insert_missing(
                session, user_team_scopes, [{"user_id": cloud_id(label), "team_id": stable_id("team")}]
            )
        else:
            profile = dict(
                session.execute(select(customers).where(customers.c.user_id == stable_id(label)))
                .mappings()
                .one()
            )
            old_id = profile["customer_id"]
            profile.update(
                customer_id=cloud_id(label + "/profile"),
                user_id=cloud_id(label),
                customer_key=cloud_id(label + "/key"),
                scenario_id="AZURE_TEAM_DEV_SYNTHETIC",
            )
            insert_missing(session, customers, [profile])
            rows = session.execute(select(orders).where(orders.c.customer_id == old_id)).mappings().all()
            for index, row in enumerate(rows):
                item = dict(row)
                item.update(
                    order_id=cloud_id(f"{label}/order/{index}"),
                    customer_id=profile["customer_id"],
                    order_number=f"AZURE-SYNTHETIC-{label}-{index}",
                    scenario_id="AZURE_TEAM_DEV_SYNTHETIC",
                )
                insert_missing(session, orders, [item])
    # Explicit grants ONLY to newly created cloud demo staff, not actual accounts.
    permissions = ["EXCEPTION_QUEUE_READ", "AUTOMATION_READ", "AUTOMATION_STOP", "RETENTION_TEAM_REVIEW"]
    insert_missing(
        session,
        staff_permissions,
        [
            {"user_id": cloud_id("admin"), "permission": p, "granted_by": cloud_id("admin")}
            for p in permissions
        ],
    )
    row = session.execute(select(automation_control)).mappings().one()
    if not row["paused"]:
        admin = session.execute(select(users).where(users.c.user_id == cloud_id("admin"))).mappings().one()
        change(session, admin, StopCommand(expected_revision=row["revision"], reason_code="OPERATOR_PAUSE"))
    audit.record(session, cloud_id("admin"), "AZURE_SYNTHETIC_SEED", "USER", None, reason="TEAM_DEV_ONLY")
    return {
        "accounts": 4,
        "source": "SYNTHETIC",
        "automatic_processing": "PAUSED",
        "full_fixture_loaded": False,
    }
