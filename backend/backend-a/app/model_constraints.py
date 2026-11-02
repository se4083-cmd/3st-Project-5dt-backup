"""Application invariants beyond the fixture field contract."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db import UTCDateTime, utcnow
from app.models import (
    analytics_batches,
    analytics_product_risk,
    assignments,
    audit_events,
    automation_jobs,
    followup_actions,
    messages,
    metadata,
    orders,
    tickets,
)

user_team_scopes = Table(
    "user_team_scopes",
    metadata,
    Column("user_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), primary_key=True),
    Column("team_id", Uuid(as_uuid=False), ForeignKey("teams.team_id"), primary_key=True),
)
team_categories = Table(
    "team_categories",
    metadata,
    Column("team_id", Uuid(as_uuid=False), ForeignKey("teams.team_id"), primary_key=True),
    Column("category", String(32), primary_key=True),
)
idempotency_keys = Table(
    "idempotency_keys",
    metadata,
    Column("user_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), primary_key=True),
    Column("key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id"), nullable=True),
    Column("followup_id", Uuid(as_uuid=False), ForeignKey("followup_actions.action_id")),
    Column("operation", String(32), nullable=False, server_default="CREATE_TICKET"),
    Column("response_snapshot", JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")),
    Column("created_at", UTCDateTime(), nullable=False, default=utcnow),
)


def check(table, name, sql):
    table.append_constraint(CheckConstraint(sql, name=name))


def unique(table, name, *columns):
    table.append_constraint(UniqueConstraint(*columns, name=name))


for table_name, columns in {
    "users": [("login_name",)],
    "customers": [("user_id",), ("customer_key",)],
    "products": [("sku",)],
    "orders": [("order_number",), ("order_id", "customer_id", "product_id")],
    "shipments": [("order_id",)],
    "returns": [("order_id",)],
    "knowledge_documents": [("policy_key", "version")],
    "automation_rules": [("rule_key", "version")],
    "ai_suggestions": [("ticket_id", "cycle_no", "revision")],
    "automation_jobs": [("ticket_id", "cycle_no")],
    "audit_events": [("event_key",)],
}.items():
    for cols in columns:
        unique(metadata.tables[table_name], "uq_" + table_name + "_" + "_".join(cols), *cols)

check(metadata.tables["users"], "role", "role IN ('CUSTOMER','AGENT','ADMIN')")
check(orders, "quantity_amount", "quantity > 0 AND amount >= 0 AND version >= 1")
check(tickets, "version_cycle", "version >= 1 AND cycle_no >= 1")
check(
    tickets,
    "status",
    "status IN ('OPEN','PROCESSING','WAITING_CUSTOMER','HANDOFF_PENDING',"
    "'ASSIGNED','IN_PROGRESS','FOLLOWUP_PENDING','RESOLVED','CANCELLED')",
)
check(tickets, "requested_mode", "requested_mode IN ('AUTO','HUMAN')")
check(tickets, "resolution_mode", "resolution_mode IS NULL OR resolution_mode IN ('AUTO','HUMAN')")
check(tickets, "order_product", "order_id IS NULL OR product_id IS NOT NULL")
check(
    tickets,
    "resolved_at",
    "status <> 'RESOLVED' OR (resolved_at IS NOT NULL AND resolution_mode IS NOT NULL)",
)
tickets.append_constraint(
    ForeignKeyConstraint(
        ["order_id", "customer_id", "product_id"],
        ["orders.order_id", "orders.customer_id", "orders.product_id"],
        name="fk_tickets_owned_order_product",
    )
)
check(messages, "cycle", "cycle_no >= 1")
check(messages, "visibility", "visibility IN ('PUBLIC','INTERNAL')")
check(messages, "role", "role IN ('CUSTOMER','AGENT','ASSISTANT','SYSTEM')")
check(messages, "direction", "direction IN ('IN','OUT','INTERNAL')")
check(
    messages,
    "public_shape",
    "visibility <> 'PUBLIC' OR ((role='CUSTOMER' AND direction='IN') "
    "OR (role IN ('AGENT','ASSISTANT','SYSTEM') AND direction='OUT'))",
)
check(messages, "body", "length(trim(body)) BETWEEN 1 AND 10000")
check(
    automation_jobs,
    "state",
    "status IN ('PENDING','RUNNING','RETRY','SUCCEEDED','FAILED','HANDED_OFF','CANCELLED')",
)
check(automation_jobs, "counters", "cycle_no >= 1 AND attempt >= 0 AND expected_ticket_version >= 1")
check(automation_jobs, "kind", "job_kind IN ('AUTO','HANDOFF')")
check(
    automation_jobs,
    "handoff_request",
    "(job_kind='AUTO' AND reason_code IS NULL) OR (job_kind='HANDOFF' "
    "AND source_message_id IS NOT NULL AND reason_code IS NOT NULL "
    "AND reason_code IN ('CUSTOMER_REQUEST','DISSATISFIED','COMPLEX_ISSUE','OTHER','HUMAN_CONTINUATION'))",
)
check(
    idempotency_keys, "operation", "operation IN ('CREATE_TICKET','REOPEN','REQUEST_AGENT','FOLLOWUP_CREATE')"
)
check(
    idempotency_keys,
    "target",
    "(operation='FOLLOWUP_CREATE' AND followup_id IS NOT NULL AND ticket_id IS NULL) "
    "OR (operation<>'FOLLOWUP_CREATE' AND followup_id IS NULL AND ticket_id IS NOT NULL)",
)
check(idempotency_keys, "snapshot", "operation='CREATE_TICKET' OR response_snapshot IS NOT NULL")
check(
    automation_jobs,
    "lease",
    "(status='RUNNING' AND lease_token IS NOT NULL AND lease_until IS NOT NULL "
    "AND lease_owner IS NOT NULL) OR (status <> 'RUNNING' AND lease_token IS NULL "
    "AND lease_until IS NULL AND lease_owner IS NULL)",
)
check(assignments, "cycle_time", "cycle_no >= 1 AND (ended_at IS NULL OR ended_at >= assigned_at)")
check(
    followup_actions,
    "target",
    "(ticket_id IS NULL AND product_id IS NOT NULL) OR (ticket_id IS NOT NULL AND product_id IS NULL)",
)
check(followup_actions, "state", "status IN ('OPEN','IN_PROGRESS','DONE','CANCELLED')")
check(
    followup_actions,
    "cycle",
    "(ticket_id IS NOT NULL AND cycle_no IS NOT NULL AND cycle_no>=1 "
    "AND responsibility_cycle_no IS NOT NULL AND responsibility_cycle_no>=cycle_no) "
    "OR (product_id IS NOT NULL AND cycle_no IS NULL AND responsibility_cycle_no IS NULL)",
)
check(followup_actions, "version", "version>=1")
check(
    followup_actions,
    "completed",
    "(status='DONE' AND completed_at IS NOT NULL) OR (status<>'DONE' AND completed_at IS NULL)",
)
check(
    followup_actions,
    "cancelled",
    "(status='CANCELLED' AND cancelled_at IS NOT NULL "
    "AND cancellation_reason IS NOT NULL AND cancellation_reason IN "
    "('CUSTOMER_WITHDREW','NO_LONGER_NEEDED','DUPLICATE','OTHER')) OR (status<>'CANCELLED' "
    "AND cancelled_at IS NULL AND cancellation_reason IS NULL)",
)
check(followup_actions, "due", "due_at IS NULL OR due_at>=created_at")
check(followup_actions, "product_block", "product_id IS NULL OR NOT blocks_resolution")
check(
    followup_actions,
    "notes",
    "(public_note IS NULL OR length(public_note)<=4000) "
    "AND (internal_note IS NULL OR length(internal_note)<=10000)",
)
check(
    analytics_batches,
    "current_success",
    "NOT is_current OR (status='SUCCEEDED' AND published_at IS NOT NULL AND validation_passed "
    "AND validated_at IS NOT NULL AND content_hash IS NOT NULL)",
)
check(
    analytics_product_risk,
    "eligible_values",
    "(data_status='ELIGIBLE' AND score IS NOT NULL AND rank IS NOT NULL AND risk_band IS NOT NULL "
    "AND score BETWEEN 0 AND 100 AND rank>0 AND risk_band IN ('NORMAL','WATCH','HIGH')) "
    "OR (data_status IN ('LOW_SAMPLE','DATA_MISSING','QUALITY_BLOCKED') "
    "AND score IS NULL AND rank IS NULL AND risk_band IS NULL)",
)
check(audit_events, "result", "result IN ('SUCCESS','DENIED','FAILURE')")

for name, table, columns, predicate in [
    ("uq_messages_final_cycle", messages, ["ticket_id", "cycle_no"], "final_reply AND direction='OUT'"),
    ("uq_assignments_current", assignments, ["ticket_id"], "ended_at IS NULL"),
    ("uq_analytics_current", analytics_batches, ["is_current"], "is_current"),
    ("uq_risk_rank", analytics_product_risk, ["batch_id", "scope_key", "rank"], "rank IS NOT NULL"),
]:
    Index(
        name,
        *(table.c[c] for c in columns),
        unique=True,
        postgresql_where=text(predicate),
        sqlite_where=text(predicate),
    )

Index("ix_orders_customer_page", orders.c.customer_id, orders.c.placed_at, orders.c.order_id)
Index("ix_tickets_customer_page", tickets.c.customer_id, tickets.c.created_at, tickets.c.ticket_id)
Index("ix_tickets_team", tickets.c.team_id, tickets.c.created_at, tickets.c.ticket_id)
Index("ix_messages_ticket_page", messages.c.ticket_id, messages.c.created_at, messages.c.message_id)
Index(
    "ix_jobs_recovery", automation_jobs.c.status, automation_jobs.c.next_attempt_at, automation_jobs.c.job_id
)
Index("ix_assignments_agent", assignments.c.agent_id, assignments.c.ticket_id, assignments.c.ended_at)
Index(
    "ix_followups_team_page",
    followup_actions.c.owner_team_id,
    followup_actions.c.created_at,
    followup_actions.c.action_id,
)
Index(
    "ix_followups_ticket",
    followup_actions.c.ticket_id,
    followup_actions.c.status,
    followup_actions.c.blocks_resolution,
)
