"""Immutable generation evidence and explicit human decisions; no business execution."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.db import UTCDateTime, utcnow
from app.extensions.p1.models import json_type
from app.models import metadata

voc_requests = sa.Table(
    "p1_voc_requests",
    metadata,
    sa.Column("request_id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column("product_id", sa.Uuid(as_uuid=False), sa.ForeignKey("products.product_id"), nullable=False),
    sa.Column("batch_id", sa.Uuid(as_uuid=False), sa.ForeignKey("analytics_receipts.batch_id")),
    sa.Column("created_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
    sa.Column("provider", sa.String(24), nullable=False),
    sa.Column("model_deployment", sa.String(128)),
    sa.Column("evidence", json_type, nullable=False),
    sa.Column("evidence_hash", sa.String(64), nullable=False),
    sa.Column("proposal", sa.JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")),
    sa.Column("reason_code", sa.String(64)),
    sa.Column("created_at", UTCDateTime(), nullable=False, default=utcnow),
    sa.Column("updated_at", UTCDateTime(), nullable=False, default=utcnow),
    sa.CheckConstraint(
        "status IN ('PENDING_REVIEW','APPROVED','REJECTED','INSUFFICIENT_DATA','FAILED')", name="status"
    ),
    sa.CheckConstraint("provider IN ('MOCK','AZURE_OPENAI')", name="provider"),
    sa.CheckConstraint("revision>=1 AND length(evidence_hash)=64", name="revision"),
    sa.CheckConstraint(
        "(status IN ('PENDING_REVIEW','APPROVED','REJECTED') AND proposal IS NOT NULL AND reason_code IS NULL) OR (status IN ('INSUFFICIENT_DATA','FAILED') AND proposal IS NULL AND reason_code IS NOT NULL)",
        name="result",
    ),
)
sa.Index("ix_p1_voc_requests_history", voc_requests.c.created_at, voc_requests.c.request_id)
voc_teams = sa.Table(
    "p1_voc_request_teams",
    metadata,
    sa.Column(
        "request_id", sa.Uuid(as_uuid=False), sa.ForeignKey("p1_voc_requests.request_id"), primary_key=True
    ),
    sa.Column("team_id", sa.Uuid(as_uuid=False), sa.ForeignKey("teams.team_id"), primary_key=True),
)
voc_reviews = sa.Table(
    "p1_voc_reviews",
    metadata,
    sa.Column("review_id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column(
        "request_id",
        sa.Uuid(as_uuid=False),
        sa.ForeignKey("p1_voc_requests.request_id"),
        nullable=False,
        unique=True,
    ),
    sa.Column("reviewed_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("decision", sa.String(16), nullable=False),
    sa.Column("reason", sa.String(500), nullable=False),
    sa.Column("created_at", UTCDateTime(), nullable=False, default=utcnow),
    sa.CheckConstraint("decision IN ('APPROVED','REJECTED')", name="decision"),
    sa.CheckConstraint("length(reason) BETWEEN 1 AND 500", name="reason"),
)
