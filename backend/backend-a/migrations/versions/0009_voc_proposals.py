"""VOC proposal evidence and human review, revision 0009 after 0008.

Frozen DDL; existing source analytics, tasks and permissions remain unchanged.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None
metadata = sa.MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)
for table, key in [
    ("users", "user_id"),
    ("products", "product_id"),
    ("analytics_receipts", "batch_id"),
    ("teams", "team_id"),
]:
    sa.Table(table, metadata, sa.Column(key, sa.Uuid(as_uuid=False), primary_key=True))
json_type = sa.JSON().with_variant(JSONB(), "postgresql")

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
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("decision IN ('APPROVED','REJECTED')", name="decision"),
    sa.CheckConstraint("length(reason) BETWEEN 1 AND 500", name="reason"),
)


def upgrade():
    for table in (voc_requests, voc_teams, voc_reviews):
        table.create(op.get_bind())


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify VOC history")
    connection = op.get_bind()
    for table in (voc_reviews, voc_teams, voc_requests):
        if connection.execute(sa.select(sa.literal(1)).select_from(table).limit(1)).first():
            raise RuntimeError("Downgrade would lose VOC history; retain 0009")
    for table in (voc_reviews, voc_teams, voc_requests):
        table.drop(connection)
