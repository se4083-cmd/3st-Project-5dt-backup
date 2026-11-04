"""Product improvement metadata; followup remains the work/owner/state authority."""

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db import UTCDateTime
from app.models import metadata

profiles = Table(
    "voc_improvement_profiles",
    metadata,
    Column("action_id", Uuid(as_uuid=False), ForeignKey("followup_actions.action_id"), primary_key=True),
    Column("product_id", Uuid(as_uuid=False), ForeignKey("products.product_id"), nullable=False),
    Column("current_plan_revision", BigInteger(), nullable=False),
    Column("created_by", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
    Column("created_at", UTCDateTime(), nullable=False),
    CheckConstraint("current_plan_revision>=1", name="revision"),
)
Index("ix_voc_profiles_product", profiles.c.product_id, profiles.c.action_id)

plans = Table(
    "voc_improvement_plan_revisions",
    metadata,
    Column("action_id", Uuid(as_uuid=False), ForeignKey(profiles.c.action_id), primary_key=True),
    Column("revision", BigInteger(), primary_key=True),
    Column("issue_code", String(64), nullable=False),
    Column("improvement_text", Text(), nullable=False),
    Column("implemented_at", UTCDateTime()),
    Column("before_start", UTCDateTime()),
    Column("before_end", UTCDateTime()),
    Column("after_start", UTCDateTime()),
    Column("after_end", UTCDateTime()),
    Column("owner_team_id_snapshot", Uuid(as_uuid=False), ForeignKey("teams.team_id"), nullable=False),
    Column("source_batch_id", Uuid(as_uuid=False), ForeignKey("analytics_batches.batch_id")),
    Column("source_scope_key", String(64)),
    Column("change_kind", String(16), nullable=False),
    Column("change_reason", String(1000), nullable=False),
    Column("created_by", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
    Column("created_at", UTCDateTime(), nullable=False),
    CheckConstraint("revision>=1", name="revision"),
    CheckConstraint("implemented_at IS NULL OR implemented_at<=created_at", name="implementation_time"),
    CheckConstraint(
        "issue_code IN ('DELIVERY_DELAY','RETURN_PROCESS','REFUND_DELAY','DAMAGED','PAYMENT_ERROR','ACCOUNT_ERROR')",
        name="issue",
    ),
    CheckConstraint(
        "length(trim(improvement_text)) BETWEEN 1 AND 4000 AND length(trim(change_reason)) BETWEEN 1 AND 1000",
        name="text",
    ),
    CheckConstraint("change_kind IN ('INITIAL','PLAN','CORRECTION')", name="change_kind"),
    CheckConstraint("(source_batch_id IS NULL) = (source_scope_key IS NULL)", name="source_pair"),
    CheckConstraint(
        "(before_start IS NULL AND before_end IS NULL AND after_start IS NULL AND after_end IS NULL) OR "
        "(before_start IS NOT NULL AND before_end IS NOT NULL AND after_start IS NOT NULL AND after_end IS NOT NULL "
        "AND implemented_at IS NOT NULL AND before_start<before_end AND after_start<after_end "
        "AND before_end<=implemented_at AND implemented_at<=after_start "
        "AND before_end-before_start=after_end-after_start)",
        name="windows",
    ),
)
Index("ix_voc_plans_source_batch", plans.c.source_batch_id)
plan_teams = Table(
    "voc_improvement_plan_teams",
    metadata,
    Column("action_id", Uuid(as_uuid=False), primary_key=True),
    Column("revision", BigInteger(), primary_key=True),
    Column("team_id", Uuid(as_uuid=False), ForeignKey("teams.team_id"), primary_key=True),
    ForeignKeyConstraint(["action_id", "revision"], [plans.c.action_id, plans.c.revision]),
)
Index("ix_voc_plan_teams_team", plan_teams.c.team_id, plan_teams.c.action_id, plan_teams.c.revision)
ticket_links = Table(
    "voc_improvement_ticket_links",
    metadata,
    Column("action_id", Uuid(as_uuid=False), ForeignKey(profiles.c.action_id), primary_key=True),
    Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id"), primary_key=True),
    Column("linked_by", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
    Column("linked_at", UTCDateTime(), nullable=False),
)
Index("ix_voc_ticket_links_ticket", ticket_links.c.ticket_id, ticket_links.c.action_id)
receipts = Table(
    "voc_improvement_receipts",
    metadata,
    Column("user_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), primary_key=True),
    Column("key", String(128), primary_key=True),
    Column("operation", String(16), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("action_id", Uuid(as_uuid=False), ForeignKey(profiles.c.action_id), nullable=False),
    Column("plan_revision", BigInteger(), nullable=False),
    Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id")),
    Column("response_snapshot", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("created_at", UTCDateTime(), nullable=False),
    ForeignKeyConstraint(["action_id", "plan_revision"], [plans.c.action_id, plans.c.revision]),
    CheckConstraint("operation IN ('CREATE','PLAN','LINK')", name="operation"),
)
Index("ix_voc_receipts_action", receipts.c.action_id)
