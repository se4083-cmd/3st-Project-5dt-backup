"""Explicit capabilities, cycle-specific routing, and durable automation control."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    Uuid,
    text,
)

from app.db import UTCDateTime, utcnow
from app.models import metadata

PERMISSIONS = (
    "EXCEPTION_QUEUE_READ",
    "UNROUTED_QUEUE_READ",
    "AUTOMATION_READ",
    "AUTOMATION_STOP",
    "AUTOMATION_RESUME",
    "RETENTION_TEAM_REVIEW",
    "RETENTION_GLOBAL_REVIEW",
    "WORKLOAD_READ",
    "VOC_IMPROVEMENT_MANAGE",
    "QUALITY_SAMPLE_MANAGE",
    "QUALITY_REVIEW",
    "QUALITY_METRICS_READ",
    "QUALITY_UNATTRIBUTED_MANAGE",
)
staff_permissions = Table(
    "staff_permissions",
    metadata,
    Column("user_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), primary_key=True),
    Column("permission", String(64), primary_key=True),
    Column("granted_by", Uuid(as_uuid=False), ForeignKey("users.user_id")),
    Column("granted_at", UTCDateTime(), nullable=False, default=utcnow),
    CheckConstraint(
        "permission IN ('EXCEPTION_QUEUE_READ','UNROUTED_QUEUE_READ','AUTOMATION_READ','AUTOMATION_STOP','AUTOMATION_RESUME','RETENTION_TEAM_REVIEW','RETENTION_GLOBAL_REVIEW','WORKLOAD_READ','VOC_IMPROVEMENT_MANAGE','QUALITY_SAMPLE_MANAGE','QUALITY_REVIEW','QUALITY_METRICS_READ','QUALITY_UNATTRIBUTED_MANAGE')",
        name="permission",
    ),
)
queue_routes = Table(
    "queue_routes",
    metadata,
    Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id"), primary_key=True),
    Column("cycle_no", BigInteger(), primary_key=True),
    Column("team_id", Uuid(as_uuid=False), ForeignKey("teams.team_id")),
    Column("revision", BigInteger(), nullable=False),
    Column("recorded_by_service", String(64), nullable=False),
    Column("recorded_at", UTCDateTime(), nullable=False, default=utcnow),
    CheckConstraint("cycle_no>=1 AND revision>=1", name="revision"),
)
automation_control = Table(
    "automation_control",
    metadata,
    Column("singleton_id", Integer(), primary_key=True),
    Column("paused", Boolean(), nullable=False, server_default=text("false")),
    Column("revision", BigInteger(), nullable=False),
    Column("generation", BigInteger(), nullable=False),
    Column("reason_code", String(64), nullable=False),
    Column("changed_by", Uuid(as_uuid=False), ForeignKey("users.user_id")),
    Column("changed_at", UTCDateTime(), nullable=False, default=utcnow),
    CheckConstraint("singleton_id=1 AND revision>=1 AND generation>=1", name="singleton"),
    CheckConstraint(
        "reason_code IN ('INITIAL_STATE','SAFETY_INCIDENT','OPERATOR_PAUSE','VERIFICATION_COMPLETE','INCIDENT_RESOLVED')",
        name="reason",
    ),
)
automation_control_history = Table(
    "automation_control_history",
    metadata,
    Column("revision", BigInteger(), primary_key=True),
    Column("generation", BigInteger(), nullable=False),
    Column("paused", Boolean(), nullable=False),
    Column("reason_code", String(64), nullable=False),
    Column("changed_by", Uuid(as_uuid=False), ForeignKey("users.user_id")),
    Column("changed_at", UTCDateTime(), nullable=False, default=utcnow),
    CheckConstraint("revision>=1 AND generation>=1", name="revision"),
    CheckConstraint(
        "reason_code IN ('INITIAL_STATE','SAFETY_INCIDENT','OPERATOR_PAUSE','VERIFICATION_COMPLETE','INCIDENT_RESOLVED')",
        name="reason",
    ),
)
