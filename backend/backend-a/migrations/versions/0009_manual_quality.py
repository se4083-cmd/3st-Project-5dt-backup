"""Prospective reply provenance and manual quality review. No legacy backfill/grants.
Revision ID: 0009; Revises: 0008.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None
OLD = "'EXCEPTION_QUEUE_READ','UNROUTED_QUEUE_READ','AUTOMATION_READ','AUTOMATION_STOP','AUTOMATION_RESUME','RETENTION_TEAM_REVIEW','RETENTION_GLOBAL_REVIEW','WORKLOAD_READ','VOC_IMPROVEMENT_MANAGE'"


def permission(values):
    with op.batch_alter_table("staff_permissions") as b:
        b.drop_constraint(op.f("ck_staff_permissions_permission"), type_="check")
        b.create_check_constraint(op.f("ck_staff_permissions_permission"), f"permission IN ({values})")


def upgrade():
    permission(
        OLD + ",'QUALITY_SAMPLE_MANAGE','QUALITY_REVIEW','QUALITY_METRICS_READ','QUALITY_UNATTRIBUTED_MANAGE'"
    )
    rubrics = op.create_table(
        "quality_rubrics",
        Column("version", String(64), primary_key=True),
        Column("status", String(32), nullable=False),
        Column("criteria", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        CheckConstraint("status='DEVELOPMENT_PROPOSAL'", name="status"),
    )
    reply_records = op.create_table(
        "automatic_reply_records",
        Column("message_id", Uuid(as_uuid=False), ForeignKey("messages.message_id"), primary_key=True),
        Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id"), nullable=False),
        Column("cycle_no", BigInteger(), nullable=False),
        Column(
            "job_id", Uuid(as_uuid=False), ForeignKey("automation_jobs.job_id"), nullable=False, unique=True
        ),
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
        Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        UniqueConstraint("ticket_id", "cycle_no"),
        CheckConstraint(
            "cycle_no>=1 AND input_ticket_revision>=1 AND result_ticket_revision=input_ticket_revision+1",
            name="revision",
        ),
        CheckConstraint("provenance_state IN ('MISSING','PARTIAL','COMPLETE')", name="provenance"),
        CheckConstraint("origin IN ('APPLICATION','SYNTHETIC','UNKNOWN')", name="origin"),
        CheckConstraint("evidence_count BETWEEN 0 AND 10", name="evidence_count"),
    )
    op.create_index(
        "ix_quality_replies_cohort",
        "automatic_reply_records",
        ["attribution_team_id", "origin", "committed_at", "message_id"],
    )
    op.create_table(
        "automatic_reply_evidence",
        Column("message_id", Uuid(as_uuid=False), ForeignKey(reply_records.c.message_id), primary_key=True),
        Column("ordinal", BigInteger(), primary_key=True),
        Column(
            "document_id", Uuid(as_uuid=False), ForeignKey("knowledge_documents.document_id"), nullable=False
        ),
        Column("document_version", BigInteger(), nullable=False),
        Column("content_hash", String(64), nullable=False),
        Column("body_sha256", String(64)),
        Column("chunk_ref", String(128)),
        CheckConstraint("ordinal>=1 AND document_version>=1", name="version"),
    )
    op.create_index("ix_quality_evidence_document", "automatic_reply_evidence", ["document_id"])
    samples = op.create_table(
        "quality_samples",
        Column("sample_id", Uuid(as_uuid=False), primary_key=True),
        Column("message_id", Uuid(as_uuid=False), ForeignKey(reply_records.c.message_id), nullable=False),
        Column("rubric_version", String(64), ForeignKey(rubrics.c.version), nullable=False),
        Column("review_team_id", Uuid(as_uuid=False), ForeignKey("teams.team_id"), nullable=False),
        Column("assigned_reviewer_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
        Column("status", String(16), nullable=False),
        Column("current_revision", BigInteger(), nullable=False),
        Column("created_by", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
        Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        UniqueConstraint("message_id", "rubric_version"),
        CheckConstraint("status IN ('OPEN','VOID') AND current_revision>=1", name="state"),
    )
    op.create_index(
        "ix_quality_samples_team", "quality_samples", ["review_team_id", "selected_at", "sample_id"]
    )
    op.create_index("ix_quality_samples_reviewer", "quality_samples", ["assigned_reviewer_id", "status"])
    revisions = op.create_table(
        "quality_review_revisions",
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
        Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
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
    op.create_table(
        "quality_command_receipts",
        Column("user_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), primary_key=True),
        Column("key", String(128), primary_key=True),
        Column("operation", String(16), nullable=False),
        Column("request_hash", String(64), nullable=False),
        Column("sample_id", Uuid(as_uuid=False), ForeignKey(samples.c.sample_id), nullable=False),
        Column("revision", BigInteger(), nullable=False),
        Column("created_at", sa.DateTime(timezone=True), nullable=False),
        ForeignKeyConstraint(["sample_id", "revision"], [revisions.c.sample_id, revisions.c.revision]),
        CheckConstraint("operation IN ('SELECT','REVIEW','REASSIGN','VOID')", name="operation"),
    )
    op.create_index("ix_quality_receipts_sample", "quality_command_receipts", ["sample_id"])
    op.bulk_insert(
        rubrics,
        [
            {
                "version": "DEV_QUALITY_V1",
                "status": "DEVELOPMENT_PROPOSAL",
                "criteria": {
                    "accuracy": "CORRECT only when recorded question and final answer support all material facts; INCORRECT for a demonstrated material factual error; otherwise UNDETERMINABLE.",
                    "policy_alignment": "MATCH/MISMATCH only against verified recorded policy bodies; absent evidence is UNDETERMINABLE. NOT_APPLICABLE is an explicit human decision, not missing evidence.",
                    "scope": "Manual selected sample; not a population accuracy estimate, autonomous safety assessment, or an agreed production rubric.",
                    "privacy": "Do not copy customer or message text into review reasons. Use the structured reason codes.",
                },
            }
        ],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION csflow_quality_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'QUALITY_HISTORY_IMMUTABLE'; END $$""")
        for table in (
            "quality_rubrics",
            "automatic_reply_records",
            "automatic_reply_evidence",
            "quality_review_revisions",
            "quality_command_receipts",
        ):
            op.execute(
                f"CREATE TRIGGER immutable_quality BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION csflow_quality_immutable()"
            )
        op.execute("""CREATE FUNCTION csflow_quality_reply_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS(SELECT 1 FROM messages m JOIN automation_jobs j ON j.job_id=NEW.job_id
             WHERE m.message_id=NEW.message_id AND m.ticket_id=NEW.ticket_id AND j.ticket_id=NEW.ticket_id
             AND m.cycle_no=NEW.cycle_no AND j.cycle_no=NEW.cycle_no AND j.job_kind='AUTO'
             AND j.expected_ticket_version=NEW.input_ticket_revision
             AND m.direction='OUT' AND m.visibility='PUBLIC' AND m.final_reply AND m.role='SYSTEM'
             AND encode(sha256(convert_to(m.body,'UTF8')),'hex')=NEW.reply_sha256) THEN
            RAISE EXCEPTION 'QUALITY_REPLY_LINK_INVALID';
          END IF;
          RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER quality_reply_guard BEFORE INSERT ON automatic_reply_records FOR EACH ROW EXECUTE FUNCTION csflow_quality_reply_guard()"
        )
        op.execute("""CREATE FUNCTION csflow_quality_evidence_count() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE mid uuid; expected bigint; actual bigint;
        BEGIN
          mid=NEW.message_id;
          SELECT evidence_count INTO expected FROM automatic_reply_records WHERE message_id=mid;
          SELECT count(*) INTO actual FROM automatic_reply_evidence WHERE message_id=mid;
          IF actual<>expected THEN RAISE EXCEPTION 'QUALITY_EVIDENCE_SEALED'; END IF;
          RETURN NULL;
        END $$""")
        for table in ("automatic_reply_records", "automatic_reply_evidence"):
            op.execute(
                f"CREATE CONSTRAINT TRIGGER sealed_quality_evidence AFTER INSERT ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION csflow_quality_evidence_count()"
            )
        op.execute("""CREATE FUNCTION csflow_quality_sample_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (NEW.sample_id,NEW.message_id,NEW.rubric_version,NEW.review_team_id,NEW.created_by,NEW.selected_at)
             IS DISTINCT FROM (OLD.sample_id,OLD.message_id,OLD.rubric_version,OLD.review_team_id,OLD.created_by,OLD.selected_at)
             OR OLD.status='VOID' OR NEW.current_revision<>OLD.current_revision+1
             OR NOT EXISTS(SELECT 1 FROM quality_review_revisions WHERE sample_id=OLD.sample_id AND revision=NEW.current_revision)
          THEN RAISE EXCEPTION 'QUALITY_SAMPLE_HISTORY_REQUIRED'; END IF;
          RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER quality_sample_guard BEFORE UPDATE ON quality_samples FOR EACH ROW EXECUTE FUNCTION csflow_quality_sample_guard()"
        )


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify quality history")
    c = op.get_bind()
    for table in ("automatic_reply_records", "quality_samples", "quality_command_receipts"):
        if c.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("Downgrade would lose quality history; retain 0009")
    if (
        c.execute(
            sa.text("SELECT 1 FROM staff_permissions WHERE permission LIKE 'QUALITY_%' LIMIT 1")
        ).first()
        or c.execute(sa.text("SELECT 1 FROM audit_events WHERE action LIKE 'QUALITY_%' LIMIT 1")).first()
    ):
        raise RuntimeError("Downgrade would lose quality authorization/history; retain 0009")
    if c.dialect.name == "postgresql":
        for function in (
            "csflow_quality_sample_guard",
            "csflow_quality_reply_guard",
            "csflow_quality_evidence_count",
            "csflow_quality_immutable",
        ):
            op.execute(f"DROP FUNCTION {function}() CASCADE")
    for table in (
        "quality_command_receipts",
        "quality_review_revisions",
        "quality_samples",
        "automatic_reply_evidence",
        "automatic_reply_records",
        "quality_rubrics",
    ):
        op.drop_table(table)
    permission(OLD)
