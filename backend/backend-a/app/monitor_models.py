"""Prospective facts only; no reconstructed legacy episodes or duplicated content."""

from sqlalchemy import (
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

from app.db import UTCDateTime
from app.models import metadata

monitor_epoch = Table(
    "automation_monitor_epoch",
    metadata,
    Column("version", String(32), primary_key=True),
    Column("recording_since", UTCDateTime(), nullable=False),
)
cycles = Table(
    "automation_cycle_records",
    metadata,
    Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id"), primary_key=True),
    Column("cycle_no", BigInteger(), primary_key=True),
    Column("entry_mode", String(8), nullable=False),
    Column("start_revision", BigInteger(), nullable=False),
    Column("started_at", UTCDateTime(), nullable=False),
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
    Column("recorded_at", UTCDateTime(), nullable=False),
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
