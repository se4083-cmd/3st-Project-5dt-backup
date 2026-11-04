"""Storage foundation only. Future target FKs arrive with VOC/policy migrations.

No task creation/worker endpoints are exposed at this stage.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.db import UTCDateTime
from app.models import metadata

json_type = sa.JSON().with_variant(JSONB(), "postgresql")
p1_idempotency = sa.Table(
    "p1_idempotency",
    metadata,
    sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.user_id"), primary_key=True),
    sa.Column("operation", sa.String(40), primary_key=True),
    sa.Column("key", sa.String(128), primary_key=True),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("response_status", sa.SmallInteger(), nullable=False),
    sa.Column("response_snapshot", json_type, nullable=False),
    sa.Column("created_at", UTCDateTime(), nullable=False),
    sa.CheckConstraint(
        "operation IN ('VOC_GENERATE','VOC_REVIEW','POLICY_REGISTER','POLICY_COMPARE','POLICY_REVIEW')",
        name="operation",
    ),
    sa.CheckConstraint("response_status IN (200,201,202)", name="response_status"),
    sa.CheckConstraint("length(request_hash)=64 AND length(key) BETWEEN 8 AND 128", name="shape"),
)
p1_tasks = sa.Table(
    "p1_tasks",
    metadata,
    sa.Column("task_id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column("kind", sa.String(32), nullable=False),
    sa.Column("voc_request_id", sa.Uuid(as_uuid=False), unique=True),
    sa.Column("policy_comparison_id", sa.Uuid(as_uuid=False), unique=True),
    sa.Column("context_key", sa.String(64), nullable=False),
    sa.Column("requested_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
    sa.Column("attempt", sa.BigInteger(), nullable=False, server_default="0"),
    sa.Column("max_attempts", sa.BigInteger(), nullable=False, server_default="3"),
    sa.Column("next_attempt_at", UTCDateTime(), nullable=False),
    sa.Column("lease_token", sa.Uuid(as_uuid=False)),
    sa.Column("lease_owner", sa.String(128)),
    sa.Column("lease_until", UTCDateTime()),
    sa.Column("automation_generation", sa.BigInteger()),
    sa.Column("error_code", sa.String(64)),
    sa.Column("created_at", UTCDateTime(), nullable=False),
    sa.Column("updated_at", UTCDateTime(), nullable=False),
    sa.Column("completed_at", UTCDateTime()),
    sa.CheckConstraint(
        "(kind='VOC_GENERATION' AND voc_request_id IS NOT NULL AND policy_comparison_id IS NULL) OR "
        "(kind='POLICY_COMPARISON' AND policy_comparison_id IS NOT NULL AND voc_request_id IS NULL)",
        name="target",
    ),
    sa.CheckConstraint(
        "status IN ('QUEUED','RUNNING','RETRY','SUCCEEDED','FAILED','CANCELLED')", name="status"
    ),
    sa.CheckConstraint(
        "revision>=1 AND attempt>=0 AND attempt<=max_attempts AND max_attempts BETWEEN 1 AND 3",
        name="counters",
    ),
    sa.CheckConstraint(
        "(status='RUNNING' AND lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_until IS NOT NULL) OR "
        "(status<>'RUNNING' AND lease_token IS NULL AND lease_owner IS NULL AND lease_until IS NULL)",
        name="lease",
    ),
    sa.CheckConstraint(
        "(status IN ('SUCCEEDED','FAILED','CANCELLED') AND completed_at IS NOT NULL) OR "
        "(status IN ('QUEUED','RUNNING','RETRY') AND completed_at IS NULL)",
        name="completed",
    ),
    sa.CheckConstraint(
        "kind<>'VOC_GENERATION' OR status<>'RUNNING' OR "
        "(automation_generation IS NOT NULL AND automation_generation>=1)",
        name="generation",
    ),
    sa.CheckConstraint("length(context_key)=64", name="context_key"),
)
sa.Index("ix_p1_tasks_claim", p1_tasks.c.status, p1_tasks.c.next_attempt_at, p1_tasks.c.task_id)
sa.Index("ix_p1_tasks_requester", p1_tasks.c.requested_by, p1_tasks.c.created_at, p1_tasks.c.task_id)
sa.Index(
    "uq_p1_tasks_active_context",
    p1_tasks.c.context_key,
    unique=True,
    postgresql_where=sa.text("status IN ('QUEUED','RUNNING','RETRY')"),
    sqlite_where=sa.text("status IN ('QUEUED','RUNNING','RETRY')"),
)
p1_ai_call_attempts = sa.Table(
    "p1_ai_call_attempts",
    metadata,
    sa.Column("call_id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column("task_id", sa.Uuid(as_uuid=False), sa.ForeignKey("p1_tasks.task_id")),
    sa.Column("automation_job_id", sa.Uuid(as_uuid=False), sa.ForeignKey("automation_jobs.job_id")),
    sa.Column("component", sa.String(24), nullable=False),
    sa.Column("source", sa.String(24), nullable=False),
    sa.Column("attempt_no", sa.Integer(), nullable=False),
    sa.Column("outcome", sa.String(16), nullable=False),
    sa.Column("error_code", sa.String(64)),
    sa.Column("provider_status", sa.SmallInteger()),
    sa.Column("started_at", UTCDateTime(), nullable=False),
    sa.Column("finished_at", UTCDateTime()),
    sa.Column("latency_ms", sa.BigInteger()),
    sa.Column("input_tokens", sa.BigInteger()),
    sa.Column("output_tokens", sa.BigInteger()),
    sa.Column("request_id", sa.Uuid(as_uuid=False)),
    sa.Column("deployment", sa.String(128)),
    sa.Column("model_version", sa.String(128)),
    sa.CheckConstraint(
        "(component='P1_VOC' AND task_id IS NOT NULL AND automation_job_id IS NULL) OR "
        "(component='BACKEND_B' AND task_id IS NULL AND automation_job_id IS NOT NULL)",
        name="target",
    ),
    sa.CheckConstraint("source IN ('MOCK','AZURE_OPENAI')", name="source"),
    sa.CheckConstraint("outcome IN ('STARTED','SUCCEEDED','FAILED','UNKNOWN')", name="outcome"),
    sa.CheckConstraint(
        "attempt_no>=1 AND (latency_ms IS NULL OR latency_ms>=0) AND "
        "(input_tokens IS NULL OR input_tokens>=0) AND (output_tokens IS NULL OR output_tokens>=0)",
        name="counters",
    ),
    sa.CheckConstraint(
        "(outcome='STARTED' AND finished_at IS NULL) OR (outcome<>'STARTED' AND finished_at IS NOT NULL)",
        name="finished",
    ),
)
sa.Index(
    "uq_p1_calls_task_attempt",
    p1_ai_call_attempts.c.task_id,
    p1_ai_call_attempts.c.attempt_no,
    unique=True,
    postgresql_where=sa.text("task_id IS NOT NULL"),
    sqlite_where=sa.text("task_id IS NOT NULL"),
)
sa.Index(
    "uq_p1_calls_job_attempt",
    p1_ai_call_attempts.c.automation_job_id,
    p1_ai_call_attempts.c.attempt_no,
    unique=True,
    postgresql_where=sa.text("automation_job_id IS NOT NULL"),
    sqlite_where=sa.text("automation_job_id IS NOT NULL"),
)
sa.Index(
    "ix_p1_calls_observation",
    p1_ai_call_attempts.c.started_at,
    p1_ai_call_attempts.c.component,
    p1_ai_call_attempts.c.outcome,
)
