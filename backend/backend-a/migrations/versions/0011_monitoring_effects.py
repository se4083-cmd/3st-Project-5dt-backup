"""Prospective monitoring and independent versioned VOC effect publication.
Revision ID: 0011; Revises: 0010. No backfill, grants, existing table changes.
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
    Index,
    String,
    Table,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
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
# DDL-only parent stubs for frozen FK resolution, never created or modified.
for name, key in [
    ("tickets", "ticket_id"),
    ("automation_jobs", "job_id"),
    ("messages", "message_id"),
    ("teams", "team_id"),
]:
    Table(name, metadata, Column(key, Uuid(as_uuid=False), primary_key=True))
Table(
    "voc_improvement_plan_revisions",
    metadata,
    Column("action_id", Uuid(as_uuid=False), primary_key=True),
    Column("revision", BigInteger(), primary_key=True),
)
monitor_epoch = Table(
    "automation_monitor_epoch",
    metadata,
    Column("version", String(32), primary_key=True),
    Column("recording_since", sa.DateTime(timezone=True), nullable=False),
)
cycles = Table(
    "automation_cycle_records",
    metadata,
    Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id"), primary_key=True),
    Column("cycle_no", BigInteger(), primary_key=True),
    Column("entry_mode", String(8), nullable=False),
    Column("start_revision", BigInteger(), nullable=False),
    Column("started_at", sa.DateTime(timezone=True), nullable=False),
    Column("origin", String(16), nullable=False),
    Column("origin_auto_cycle_no", BigInteger()),
    CheckConstraint("cycle_no>=1 AND start_revision>=1", name="revision"),
    CheckConstraint("entry_mode IN ('AUTO','HUMAN')", name="mode"),
    CheckConstraint("origin IN ('APPLICATION','SYNTHETIC','UNKNOWN')", name="origin"),
    ForeignKeyConstraint(
        ["ticket_id", "origin_auto_cycle_no"],
        ["automation_cycle_records.ticket_id", "automation_cycle_records.cycle_no"],
    ),
)
Index("ix_monitor_cycles_cohort", cycles.c.started_at, cycles.c.origin)
events = Table(
    "automation_cycle_events",
    metadata,
    Column("ticket_id", Uuid(as_uuid=False), primary_key=True),
    Column("cycle_no", BigInteger(), primary_key=True),
    Column("event_key", String(96), primary_key=True),
    Column("kind", String(24), nullable=False),
    Column("ticket_revision", BigInteger(), nullable=False),
    Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    Column("job_id", Uuid(as_uuid=False), ForeignKey("automation_jobs.job_id")),
    Column("message_id", Uuid(as_uuid=False), ForeignKey("messages.message_id")),
    Column("team_id", Uuid(as_uuid=False), ForeignKey("teams.team_id")),
    Column("reason_code", String(32), nullable=False),
    Column("writer", String(8), nullable=False),
    Column("request_hash", String(64), nullable=False),
    ForeignKeyConstraint(
        ["ticket_id", "cycle_no"], ["automation_cycle_records.ticket_id", "automation_cycle_records.cycle_no"]
    ),
    CheckConstraint(
        "kind IN ('ROUTED','AUTO_COMMITTED','TRANSFER','RECONTACT','FAILED','RETRY')", name="kind"
    ),
    CheckConstraint("writer IN ('A','B') AND ticket_revision>=1", name="writer"),
    CheckConstraint(
        "reason_code IN ('NONE','CUSTOMER_REQUEST','DISSATISFIED','COMPLEX_ISSUE','OTHER','REOPENED','RETRY_EXHAUSTED','POLICY','LOW_CONFIDENCE','UNKNOWN')",
        name="reason",
    ),
)
Index("ix_monitor_events_message", events.c.message_id)
Index("ix_monitor_events_job", events.c.job_id)

effect_batches = Table(
    "voc_effect_batches",
    metadata,
    Column("batch_id", Uuid(as_uuid=False), primary_key=True),
    Column("action_id", Uuid(as_uuid=False), nullable=False),
    Column("plan_revision", BigInteger(), nullable=False),
    Column("origin", String(16), nullable=False),
    Column("source_as_of", sa.DateTime(timezone=True), nullable=False),
    Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("payload", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("status", String(16), nullable=False),
    Column("validation", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("received_at", sa.DateTime(timezone=True), nullable=False),
    Column("published_at", sa.DateTime(timezone=True)),
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

NEW = [monitor_epoch, cycles, events, effect_batches, effect_current]


def upgrade():
    for table in NEW:
        op.execute(sa.schema.CreateTable(table))
        for index in table.indexes:
            op.execute(sa.schema.CreateIndex(index))
    op.execute(
        "INSERT INTO automation_monitor_epoch(version,recording_since) VALUES ('AUTO_CYCLE_V1',CURRENT_TIMESTAMP)"
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """CREATE FUNCTION monitor_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'monitor/effect history is immutable'; END $$"""
        )
        for name in ["automation_monitor_epoch", "automation_cycle_records", "automation_cycle_events"]:
            op.execute(
                f"CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION monitor_immutable()"
            )
        op.execute("""CREATE FUNCTION monitor_worker_fact_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE j automation_jobs; t tickets;
        BEGIN
          IF NEW.writer='B' THEN
            SELECT * INTO j FROM automation_jobs WHERE job_id=NEW.job_id;
            SELECT * INTO t FROM tickets WHERE ticket_id=NEW.ticket_id;
            IF j.job_id IS NULL OR j.ticket_id<>NEW.ticket_id OR j.cycle_no<>NEW.cycle_no OR j.job_kind<>'AUTO'
               OR j.lease_token IS NOT NULL OR j.lease_owner IS NOT NULL OR j.lease_until IS NOT NULL THEN
              RAISE EXCEPTION 'B fact requires same transaction final job and cleared lease';
            END IF;
            IF (NEW.kind='RETRY' AND j.status<>'RETRY') OR (NEW.kind IN ('FAILED','TRANSFER') AND j.status<>'FAILED') THEN
              RAISE EXCEPTION 'B fact outcome mismatch';
            END IF;
            IF NEW.kind='TRANSFER' AND (t.requested_mode<>'HUMAN' OR t.status<>'HANDOFF_PENDING'
               OR t.cycle_no<>NEW.cycle_no OR t.version<>NEW.ticket_revision+1) THEN
              RAISE EXCEPTION 'B transfer requires atomic HUMAN transition';
            END IF;
          END IF;
          RETURN NEW;
        END $$""")
        op.execute(
            "CREATE CONSTRAINT TRIGGER monitor_worker_fact_guard AFTER INSERT ON automation_cycle_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION monitor_worker_fact_guard()"
        )
        op.execute("""CREATE FUNCTION effect_batch_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF TG_OP='DELETE' OR OLD.status IN ('SUCCEEDED','FAILED') THEN
            RAISE EXCEPTION 'effect receipt immutable';
          END IF;
          IF (to_jsonb(NEW)-ARRAY['status','validation','published_at']) IS DISTINCT FROM
             (to_jsonb(OLD)-ARRAY['status','validation','published_at']) THEN
            RAISE EXCEPTION 'effect payload immutable';
          END IF;
          IF NOT ((OLD.status='RECEIVED' AND NEW.status IN ('VALIDATED','FAILED')) OR (OLD.status='VALIDATED' AND NEW.status='SUCCEEDED')) THEN
            RAISE EXCEPTION 'invalid effect transition';
          END IF;
          RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER effect_batch_guard BEFORE UPDATE OR DELETE ON voc_effect_batches FOR EACH ROW EXECUTE FUNCTION effect_batch_guard()"
        )
        op.execute("""CREATE FUNCTION effect_pointer_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NOT EXISTS(SELECT 1 FROM voc_effect_batches b WHERE b.batch_id=NEW.batch_id AND b.status='SUCCEEDED'
             AND b.action_id=NEW.action_id AND b.plan_revision=NEW.plan_revision AND b.origin=NEW.origin) THEN
             RAISE EXCEPTION 'effect pointer mismatch';
          END IF;
          RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER effect_pointer_guard BEFORE INSERT OR UPDATE ON voc_effect_publication FOR EACH ROW EXECUTE FUNCTION effect_pointer_guard()"
        )
    else:
        for name in ["automation_monitor_epoch", "automation_cycle_records", "automation_cycle_events"]:
            for event in ["UPDATE", "DELETE"]:
                op.execute(
                    f"CREATE TRIGGER immutable_{name}_{event} BEFORE {event} ON {name} BEGIN SELECT RAISE(ABORT,'immutable history'); END"
                )


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Cannot verify monitoring/effect history offline; retain 0011")
    for table in NEW[1:]:
        if op.get_bind().execute(sa.text(f"SELECT 1 FROM {table.name} LIMIT 1")).first():
            raise RuntimeError("History exists; retain 0011")
    for table in reversed(NEW):
        op.execute(sa.schema.DropTable(table))
    if op.get_bind().dialect.name == "postgresql":
        for name in [
            "effect_pointer_guard",
            "effect_batch_guard",
            "monitor_worker_fact_guard",
            "monitor_immutable",
        ]:
            op.execute(f"DROP FUNCTION {name}()")
