"""Policy review workspace, revision 0010 after 0009. Frozen DDL, no activation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
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
for name, key in [("users", "user_id"), ("teams", "team_id"), ("knowledge_documents", "document_id")]:
    sa.Table(name, metadata, sa.Column(key, sa.Uuid(as_uuid=False), primary_key=True))
json_type = sa.JSON().with_variant(JSONB(), "postgresql")
policies = sa.Table(
    "p1_policies",
    metadata,
    sa.Column("policy_id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column("policy_key", sa.String(64), nullable=False),
    sa.Column("scope_hash", sa.String(64), nullable=False),
    sa.Column("latest_version", sa.BigInteger(), nullable=False),
    sa.Column("created_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("scope_hash", "policy_key", name="uq_p1_policies_scope_key"),
    sa.CheckConstraint("latest_version>=1 AND length(scope_hash)=64", name="version"),
)
policy_teams = sa.Table(
    "p1_policy_teams",
    metadata,
    sa.Column("policy_id", sa.Uuid(as_uuid=False), sa.ForeignKey("p1_policies.policy_id"), primary_key=True),
    sa.Column("team_id", sa.Uuid(as_uuid=False), sa.ForeignKey("teams.team_id"), primary_key=True),
)
policy_versions = sa.Table(
    "p1_policy_versions",
    metadata,
    sa.Column("version_id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column("policy_id", sa.Uuid(as_uuid=False), sa.ForeignKey("p1_policies.policy_id"), nullable=False),
    sa.Column("version_no", sa.BigInteger(), nullable=False),
    sa.Column("title", sa.String(200), nullable=False),
    sa.Column("body", sa.Text(), nullable=False),
    sa.Column("content_hash", sa.String(64), nullable=False),
    sa.Column("source_document_id", sa.Uuid(as_uuid=False), sa.ForeignKey("knowledge_documents.document_id")),
    sa.Column("source_snapshot", json_type, nullable=False),
    sa.Column("status", sa.String(24), nullable=False, server_default="PENDING_REVIEW"),
    sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
    sa.Column("created_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("policy_id", "version_no", name="uq_p1_policy_versions_number"),
    sa.CheckConstraint("version_no>=1 AND revision>=1 AND length(content_hash)=64", name="version"),
    sa.CheckConstraint("status IN ('PENDING_REVIEW','APPROVED','REJECTED')", name="status"),
    sa.CheckConstraint(
        "length(title) BETWEEN 1 AND 200 AND length(body) BETWEEN 1 AND 20000", name="content"
    ),
)
policy_comparisons = sa.Table(
    "p1_policy_comparisons",
    metadata,
    sa.Column("comparison_id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column("policy_id", sa.Uuid(as_uuid=False), sa.ForeignKey("p1_policies.policy_id"), nullable=False),
    sa.Column("from_version_id", sa.Uuid(as_uuid=False), sa.ForeignKey("p1_policy_versions.version_id")),
    sa.Column(
        "to_version_id",
        sa.Uuid(as_uuid=False),
        sa.ForeignKey("p1_policy_versions.version_id"),
        nullable=False,
    ),
    sa.Column("diff", json_type, nullable=False),
    sa.Column("impact", json_type, nullable=False),
    sa.Column("analysis_hash", sa.String(64), nullable=False),
    sa.Column("status", sa.String(24), nullable=False, server_default="PENDING_REVIEW"),
    sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
    sa.Column("created_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('PENDING_REVIEW','APPROVED','REJECTED')", name="status"),
    sa.CheckConstraint("revision>=1 AND length(analysis_hash)=64", name="revision"),
    sa.CheckConstraint("from_version_id IS NULL OR from_version_id<>to_version_id", name="pair"),
)
sa.Index(
    "ix_p1_policy_comparisons_history", policy_comparisons.c.created_at, policy_comparisons.c.comparison_id
)
policy_reviews = sa.Table(
    "p1_policy_reviews",
    metadata,
    sa.Column("review_id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column(
        "comparison_id",
        sa.Uuid(as_uuid=False),
        sa.ForeignKey("p1_policy_comparisons.comparison_id"),
        nullable=False,
        unique=True,
    ),
    sa.Column(
        "version_id",
        sa.Uuid(as_uuid=False),
        sa.ForeignKey("p1_policy_versions.version_id"),
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
    for table in (policies, policy_teams, policy_versions, policy_comparisons, policy_reviews):
        table.create(op.get_bind())


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify policy history")
    connection = op.get_bind()
    for table in (policy_reviews, policy_comparisons, policy_versions, policy_teams, policies):
        if connection.execute(sa.select(sa.literal(1)).select_from(table).limit(1)).first():
            raise RuntimeError("Downgrade would lose policy history; retain 0010")
    for table in (policy_reviews, policy_comparisons, policy_versions, policy_teams, policies):
        table.drop(connection)
