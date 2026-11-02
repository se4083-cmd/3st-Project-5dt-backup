"""Followup lifecycle, origin/responsibility, and global creation idempotency.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CHECKS = {
    "cycle": "(ticket_id IS NOT NULL AND cycle_no IS NOT NULL AND cycle_no>=1 "
    "AND responsibility_cycle_no IS NOT NULL AND responsibility_cycle_no>=cycle_no) "
    "OR (product_id IS NOT NULL AND cycle_no IS NULL AND responsibility_cycle_no IS NULL)",
    "version": "version>=1",
    "completed": "(status='DONE' AND completed_at IS NOT NULL) OR (status<>'DONE' AND completed_at IS NULL)",
    "cancelled": "(status='CANCELLED' AND cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL "
    "AND cancellation_reason IN ('CUSTOMER_WITHDREW','NO_LONGER_NEEDED','DUPLICATE','OTHER')) "
    "OR (status<>'CANCELLED' AND cancelled_at IS NULL AND cancellation_reason IS NULL)",
    "due": "due_at IS NULL OR due_at>=created_at",
    "product_block": "product_id IS NULL OR NOT blocks_resolution",
    "notes": "(public_note IS NULL OR length(public_note)<=4000) AND "
    "(internal_note IS NULL OR length(internal_note)<=10000)",
}


def upgrade():
    op.add_column("followup_actions", sa.Column("origin_team_id", sa.Uuid(as_uuid=False)))
    op.add_column("followup_actions", sa.Column("responsibility_cycle_no", sa.BigInteger()))
    op.add_column("followup_actions", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.add_column("followup_actions", sa.Column("cancellation_reason", sa.String(64)))
    op.execute("UPDATE followup_actions SET origin_team_id=owner_team_id, responsibility_cycle_no=cycle_no")
    with op.batch_alter_table("followup_actions") as b:
        b.alter_column("origin_team_id", existing_type=sa.Uuid(as_uuid=False), nullable=False)
        b.create_foreign_key(
            op.f("fk_followup_actions_origin_team_id_teams"), "teams", ["origin_team_id"], ["team_id"]
        )
        for name, sql in CHECKS.items():
            b.create_check_constraint(op.f("ck_followup_actions_" + name), sql)
    op.create_index(
        "ix_followups_team_page", "followup_actions", ["owner_team_id", "created_at", "action_id"]
    )
    op.create_index("ix_followups_ticket", "followup_actions", ["ticket_id", "status", "blocks_resolution"])
    with op.batch_alter_table("idempotency_keys") as b:
        b.alter_column("ticket_id", existing_type=sa.Uuid(as_uuid=False), nullable=True)
        b.add_column(sa.Column("followup_id", sa.Uuid(as_uuid=False)))
        b.create_foreign_key(
            op.f("fk_idempotency_keys_followup_id_followup_actions"),
            "followup_actions",
            ["followup_id"],
            ["action_id"],
        )
        b.drop_constraint(op.f("ck_idempotency_keys_operation"), type_="check")
        b.create_check_constraint(
            op.f("ck_idempotency_keys_operation"),
            "operation IN ('CREATE_TICKET','REOPEN','REQUEST_AGENT','FOLLOWUP_CREATE')",
        )
        b.create_check_constraint(
            op.f("ck_idempotency_keys_target"),
            "(operation='FOLLOWUP_CREATE' AND followup_id IS NOT NULL AND ticket_id IS NULL) "
            "OR (operation<>'FOLLOWUP_CREATE' AND followup_id IS NULL AND ticket_id IS NOT NULL)",
        )


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify followup history")
    if op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM audit_events WHERE data_origin='APPLICATION' "
            "AND action IN ('FOLLOWUP_CREATED','FOLLOWUP_UPDATED','FOLLOWUP_STATE_CHANGED') LIMIT 1"
        )
    ).first() or (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM idempotency_keys WHERE operation='FOLLOWUP_CREATE' LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Downgrade would lose followup history; retain 0003")
    with op.batch_alter_table("idempotency_keys") as b:
        b.drop_constraint(op.f("ck_idempotency_keys_target"), type_="check")
        b.drop_constraint(op.f("ck_idempotency_keys_operation"), type_="check")
        b.create_check_constraint(
            op.f("ck_idempotency_keys_operation"), "operation IN ('CREATE_TICKET','REOPEN','REQUEST_AGENT')"
        )
        b.drop_constraint(op.f("fk_idempotency_keys_followup_id_followup_actions"), type_="foreignkey")
        b.drop_column("followup_id")
        b.alter_column("ticket_id", existing_type=sa.Uuid(as_uuid=False), nullable=False)
    op.drop_index("ix_followups_ticket", table_name="followup_actions")
    op.drop_index("ix_followups_team_page", table_name="followup_actions")
    with op.batch_alter_table("followup_actions") as b:
        for name in CHECKS:
            b.drop_constraint(op.f("ck_followup_actions_" + name), type_="check")
        b.drop_constraint(op.f("fk_followup_actions_origin_team_id_teams"), type_="foreignkey")
        for name in ["origin_team_id", "responsibility_cycle_no", "cancelled_at", "cancellation_reason"]:
            b.drop_column(name)
