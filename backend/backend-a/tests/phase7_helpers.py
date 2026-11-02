"""Local synthetic custody fixtures; never an assignment or retention engine."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app import models as m
from app.analytics_canonical import digest
from app.schema import metadata
from app.seed import stable_id
from app.staff_models import staff_permissions

AS_OF = datetime(2026, 10, 31, 3, tzinfo=timezone.utc)
OLD = AS_OF - timedelta(days=120)
URL = "/api/v1/staff/retention/dry-run"
BODY = {"purpose_code": "RETENTION_REVIEW", "as_of": AS_OF.isoformat(), "scope": "GLOBAL"}


def grant(factory, label="admin", permission="RETENTION_GLOBAL_REVIEW"):
    with factory.begin() as s:
        s.execute(staff_permissions.insert().values(user_id=stable_id(label), permission=permission))


def archived(factory, *, team="team", cycle=2, at=OLD, **changes):
    tid, mid = str(uuid4()), str(uuid4())
    with factory.begin() as s:
        values = dict(
            ticket_id=tid,
            customer_id=stable_id("customer1/profile"),
            team_id=stable_id(team) if team else None,
            status="RESOLVED",
            resolved_at=at,
            resolution_mode="HUMAN",
            requested_mode="HUMAN",
            category="DELIVERY",
            cycle_no=cycle,
            sla_due_at=at,
            created_at=at,
            updated_at=at,
        )
        values.update(changes)
        s.execute(m.tickets.insert().values(**values))
        s.execute(
            m.messages.insert().values(
                message_id=mid,
                ticket_id=tid,
                cycle_no=1,
                role="CUSTOMER",
                direction="IN",
                body="PRIVATE_RETENTION_ORIGINAL",
                created_at=at,
                updated_at=at,
            )
        )
    return tid, mid


def target(report, name):
    return next(t for t in report["targets"] if t["target"] == name)


def business_hashes(factory):
    # Test-only byte/content equality. Only hashes leave the test transaction;
    # production preview does not SELECT these payload columns.
    with factory() as s:
        return {
            name: digest(sorted([dict(r) for r in s.execute(select(t)).mappings()], key=lambda r: digest(r)))
            for name, t in metadata.tables.items()
            if name not in {"audit_events"}
        }
