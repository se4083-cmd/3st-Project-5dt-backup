"""Customer cycles, global command idempotency, and durable human handoff.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("idempotency_keys") as batch:
        batch.drop_constraint("uq_idempotency_keys_ticket_id", type_="unique")
        batch.add_column(
            sa.Column("operation", sa.String(32), nullable=False, server_default="CREATE_TICKET")
        )
        batch.add_column(
            sa.Column(
                "response_snapshot",
                sa.JSON(none_as_null=True).with_variant(postgresql.JSONB(none_as_null=True), "postgresql"),
                nullable=True,
            )
        )
        batch.create_check_constraint(
            op.f("ck_idempotency_keys_operation"), "operation IN ('CREATE_TICKET','REOPEN','REQUEST_AGENT')"
        )
        batch.create_check_constraint(
            op.f("ck_idempotency_keys_snapshot"), "operation='CREATE_TICKET' OR response_snapshot IS NOT NULL"
        )
    with op.batch_alter_table("automation_jobs") as batch:
        batch.add_column(sa.Column("job_kind", sa.String(16), nullable=False, server_default="AUTO"))
        batch.add_column(sa.Column("source_message_id", sa.Uuid(as_uuid=False), nullable=True))
        batch.add_column(sa.Column("reason_code", sa.String(64), nullable=True))
        batch.create_foreign_key(
            op.f("fk_automation_jobs_source_message_id_messages"),
            "messages",
            ["source_message_id"],
            ["message_id"],
        )
        batch.create_check_constraint(op.f("ck_automation_jobs_kind"), "job_kind IN ('AUTO','HANDOFF')")
        batch.create_check_constraint(
            op.f("ck_automation_jobs_handoff_request"),
            "(job_kind='AUTO' AND reason_code IS NULL) OR (job_kind='HANDOFF' "
            "AND source_message_id IS NOT NULL AND reason_code IS NOT NULL "
            "AND reason_code IN ('CUSTOMER_REQUEST','DISSATISFIED','COMPLEX_ISSUE','OTHER','HUMAN_CONTINUATION'))",
        )


def downgrade():
    # Never delete successful commands to force the old ticket_id UNIQUE to fit.
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify command history; use a reviewed online migration")
    if not op.get_context().as_sql:
        duplicate = (
            op.get_bind()
            .execute(
                sa.text(
                    "SELECT ticket_id FROM idempotency_keys GROUP BY ticket_id HAVING count(*) > 1 LIMIT 1"
                )
            )
            .first()
        )
        commands = (
            op.get_bind()
            .execute(sa.text("SELECT 1 FROM idempotency_keys WHERE operation <> 'CREATE_TICKET' LIMIT 1"))
            .first()
        )
        handoffs = (
            op.get_bind()
            .execute(sa.text("SELECT 1 FROM automation_jobs WHERE job_kind='HANDOFF' LIMIT 1"))
            .first()
        )
        if duplicate or commands or handoffs:
            raise RuntimeError(
                "Downgrade would lose command history; retain 0002 and restore a compatible release"
            )
    with op.batch_alter_table("automation_jobs") as batch:
        batch.drop_constraint(op.f("ck_automation_jobs_handoff_request"), type_="check")
        batch.drop_constraint(op.f("ck_automation_jobs_kind"), type_="check")
        batch.drop_constraint(op.f("fk_automation_jobs_source_message_id_messages"), type_="foreignkey")
        batch.drop_column("reason_code")
        batch.drop_column("source_message_id")
        batch.drop_column("job_kind")
    with op.batch_alter_table("idempotency_keys") as batch:
        batch.drop_constraint(op.f("ck_idempotency_keys_snapshot"), type_="check")
        batch.drop_constraint(op.f("ck_idempotency_keys_operation"), type_="check")
        batch.drop_column("response_snapshot")
        batch.drop_column("operation")
        batch.create_unique_constraint("uq_idempotency_keys_ticket_id", ["ticket_id"])
