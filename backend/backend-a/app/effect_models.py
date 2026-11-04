"""Independent versioned effect receipt/publication; analytics-v1 is untouched."""

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
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db import UTCDateTime
from app.models import metadata

effect_batches = Table(
    "voc_effect_batches",
    metadata,
    Column("batch_id", Uuid(as_uuid=False), primary_key=True),
    Column("action_id", Uuid(as_uuid=False), nullable=False),
    Column("plan_revision", BigInteger(), nullable=False),
    Column("origin", String(16), nullable=False),
    Column("source_as_of", UTCDateTime(), nullable=False),
    Column("generated_at", UTCDateTime(), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("payload", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("status", String(16), nullable=False),
    Column("validation", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("received_at", UTCDateTime(), nullable=False),
    Column("published_at", UTCDateTime()),
    ForeignKeyConstraint(
        ["action_id", "plan_revision"],
        ["voc_improvement_plan_revisions.action_id", "voc_improvement_plan_revisions.revision"],
    ),
    CheckConstraint("status IN ('RECEIVED','VALIDATED','FAILED','SUCCEEDED')", name="status"),
    CheckConstraint("origin IN ('OPERATIONAL','SYNTHETIC') AND plan_revision>=1", name="origin"),
)
Index(
    "ix_effect_action_plan",
    effect_batches.c.action_id,
    effect_batches.c.plan_revision,
    effect_batches.c.origin,
)
effect_current = Table(
    "voc_effect_publication",
    metadata,
    Column("action_id", Uuid(as_uuid=False), primary_key=True),
    Column("plan_revision", BigInteger(), primary_key=True),
    Column("origin", String(16), primary_key=True),
    Column("batch_id", Uuid(as_uuid=False), ForeignKey("voc_effect_batches.batch_id"), nullable=False),
    ForeignKeyConstraint(
        ["action_id", "plan_revision"],
        ["voc_improvement_plan_revisions.action_id", "voc_improvement_plan_revisions.revision"],
    ),
    CheckConstraint("origin IN ('OPERATIONAL','SYNTHETIC')", name="origin"),
)
