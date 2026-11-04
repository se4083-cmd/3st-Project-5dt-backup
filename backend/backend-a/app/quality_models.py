"""Prospective confirmed replies and manual QA; never raw material copies."""

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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db import UTCDateTime
from app.models import metadata

rubrics = Table(
    "quality_rubrics",
    metadata,
    Column("version", String(64), primary_key=True),
    Column("status", String(32), nullable=False),
    Column("criteria", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    CheckConstraint("status='DEVELOPMENT_PROPOSAL'", name="status"),
)
reply_records = Table(
    "automatic_reply_records",
    metadata,
    Column("message_id", Uuid(as_uuid=False), ForeignKey("messages.message_id"), primary_key=True),
    Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id"), nullable=False),
    Column("cycle_no", BigInteger(), nullable=False),
    Column("job_id", Uuid(as_uuid=False), ForeignKey("automation_jobs.job_id"), nullable=False, unique=True),
    Column("input_ticket_revision", BigInteger(), nullable=False),
    Column("result_ticket_revision", BigInteger(), nullable=False),
    Column("reply_sha256", String(64), nullable=False),
    Column("source_message_id", Uuid(as_uuid=False), ForeignKey("messages.message_id")),
    Column("question_sha256", String(64)),
    Column("suggestion_id", Uuid(as_uuid=False), ForeignKey("ai_suggestions.suggestion_id")),
    Column("suggestion_revision", BigInteger()),
    Column("suggestion_content_hash", String(64)),
    Column("approval_id", Uuid(as_uuid=False), ForeignKey("approvals.approval_id")),
    Column("approval_reviewer_id", Uuid(as_uuid=False), ForeignKey("users.user_id")),
    Column("model_version", String(128)),
    Column("prompt_version", String(128)),
    Column("retrieval_ref", String(128)),
    Column("attribution_team_id", Uuid(as_uuid=False), ForeignKey("teams.team_id")),
    Column("provenance_state", String(16), nullable=False),
    Column("evidence_count", BigInteger(), nullable=False),
    Column("origin", String(16), nullable=False),
    Column("committed_at", UTCDateTime(), nullable=False),
    UniqueConstraint("ticket_id", "cycle_no"),
    CheckConstraint(
        "cycle_no>=1 AND input_ticket_revision>=1 AND result_ticket_revision=input_ticket_revision+1",
        name="revision",
    ),
    CheckConstraint("provenance_state IN ('MISSING','PARTIAL','COMPLETE')", name="provenance"),
    CheckConstraint("origin IN ('APPLICATION','SYNTHETIC','UNKNOWN')", name="origin"),
    CheckConstraint("evidence_count BETWEEN 0 AND 10", name="evidence_count"),
)
Index(
    "ix_quality_replies_cohort",
    reply_records.c.attribution_team_id,
    reply_records.c.origin,
    reply_records.c.committed_at,
    reply_records.c.message_id,
)
evidence = Table(
    "automatic_reply_evidence",
    metadata,
    Column("message_id", Uuid(as_uuid=False), ForeignKey(reply_records.c.message_id), primary_key=True),
    Column("ordinal", BigInteger(), primary_key=True),
    Column("document_id", Uuid(as_uuid=False), ForeignKey("knowledge_documents.document_id"), nullable=False),
    Column("document_version", BigInteger(), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("body_sha256", String(64)),
    Column("chunk_ref", String(128)),
    CheckConstraint("ordinal>=1 AND document_version>=1", name="version"),
)
Index("ix_quality_evidence_document", evidence.c.document_id)
samples = Table(
    "quality_samples",
    metadata,
    Column("sample_id", Uuid(as_uuid=False), primary_key=True),
    Column("message_id", Uuid(as_uuid=False), ForeignKey(reply_records.c.message_id), nullable=False),
    Column("rubric_version", String(64), ForeignKey(rubrics.c.version), nullable=False),
    Column("review_team_id", Uuid(as_uuid=False), ForeignKey("teams.team_id"), nullable=False),
    Column("assigned_reviewer_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
    Column("status", String(16), nullable=False),
    Column("current_revision", BigInteger(), nullable=False),
    Column("created_by", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
    Column("selected_at", UTCDateTime(), nullable=False),
    UniqueConstraint("message_id", "rubric_version"),
    CheckConstraint("status IN ('OPEN','VOID') AND current_revision>=1", name="state"),
)
Index("ix_quality_samples_team", samples.c.review_team_id, samples.c.selected_at, samples.c.sample_id)
Index("ix_quality_samples_reviewer", samples.c.assigned_reviewer_id, samples.c.status)
revisions = Table(
    "quality_review_revisions",
    metadata,
    Column("sample_id", Uuid(as_uuid=False), ForeignKey(samples.c.sample_id), primary_key=True),
    Column("revision", BigInteger(), primary_key=True),
    Column("event_kind", String(16), nullable=False),
    Column("actor_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
    Column("assigned_reviewer_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
    Column("accuracy", String(24)),
    Column("policy_alignment", String(24)),
    Column("reason_codes", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("change_reason", String(64), nullable=False),
    Column("independent_review", String(16), nullable=False),
    Column("recorded_at", UTCDateTime(), nullable=False),
    CheckConstraint("revision>=1 AND event_kind IN ('SELECT','REVIEW','REASSIGN','VOID')", name="event"),
    CheckConstraint(
        "(event_kind='REVIEW' AND accuracy IS NOT NULL AND policy_alignment IS NOT NULL) OR (event_kind<>'REVIEW' AND accuracy IS NULL AND policy_alignment IS NULL)",
        name="judgment",
    ),
    CheckConstraint(
        "accuracy IS NULL OR accuracy IN ('CORRECT','INCORRECT','UNDETERMINABLE')", name="accuracy"
    ),
    CheckConstraint(
        "policy_alignment IS NULL OR policy_alignment IN ('MATCH','MISMATCH','UNDETERMINABLE','NOT_APPLICABLE')",
        name="policy",
    ),
    CheckConstraint("independent_review IN ('YES','NO','UNKNOWN')", name="independence"),
)
receipts = Table(
    "quality_command_receipts",
    metadata,
    Column("user_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), primary_key=True),
    Column("key", String(128), primary_key=True),
    Column("operation", String(16), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("sample_id", Uuid(as_uuid=False), ForeignKey(samples.c.sample_id), nullable=False),
    Column("revision", BigInteger(), nullable=False),
    Column("created_at", UTCDateTime(), nullable=False),
    ForeignKeyConstraint(["sample_id", "revision"], [revisions.c.sample_id, revisions.c.revision]),
    CheckConstraint("operation IN ('SELECT','REVIEW','REASSIGN','VOID')", name="operation"),
)
Index("ix_quality_receipts_sample", receipts.c.sample_id)
