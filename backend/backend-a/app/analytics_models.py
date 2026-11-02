"""Staging receipt and singleton snapshot pointer; existing four marts are reused."""

from sqlalchemy import JSON, CheckConstraint, Column, ForeignKey, Integer, String, Table, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.db import UTCDateTime, utcnow
from app.models import metadata

analytics_receipts = Table(
    "analytics_receipts",
    metadata,
    Column("batch_id", Uuid(as_uuid=False), ForeignKey("analytics_batches.batch_id"), primary_key=True),
    Column("content_hash", String(64), nullable=False),
    Column("payload", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("validation_result", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("received_at", UTCDateTime(), nullable=False, default=utcnow),
)
analytics_publication = Table(
    "analytics_publication",
    metadata,
    Column("singleton_id", Integer(), primary_key=True),
    Column("batch_id", Uuid(as_uuid=False), ForeignKey("analytics_receipts.batch_id")),
    CheckConstraint("singleton_id=1", name="singleton"),
)
