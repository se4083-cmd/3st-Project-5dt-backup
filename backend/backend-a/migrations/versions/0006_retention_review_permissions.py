"""Explicit retention review capabilities only; no deletion or data expiry.

Revision ID: 0006; Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

OLD = "'EXCEPTION_QUEUE_READ','UNROUTED_QUEUE_READ','AUTOMATION_READ','AUTOMATION_STOP','AUTOMATION_RESUME'"


def constraint(values):
    # Only this small capability table is rebuilt on SQLite; no business rows.
    with op.batch_alter_table("staff_permissions") as batch:
        batch.drop_constraint(op.f("ck_staff_permissions_permission"), type_="check")
        batch.create_check_constraint(op.f("ck_staff_permissions_permission"), f"permission IN ({values})")


def upgrade():
    constraint(OLD + ",'RETENTION_TEAM_REVIEW','RETENTION_GLOBAL_REVIEW'")
    # No permission grants or business data changes.


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify retention review history")
    c = op.get_bind()
    if (
        c.execute(
            sa.text(
                "SELECT 1 FROM staff_permissions WHERE permission IN ('RETENTION_TEAM_REVIEW','RETENTION_GLOBAL_REVIEW') LIMIT 1"
            )
        ).first()
        or c.execute(sa.text("SELECT 1 FROM audit_events WHERE action='RETENTION_DRY_RUN' LIMIT 1")).first()
    ):
        raise RuntimeError("Downgrade would lose retention review authorization/history; retain 0006")
    constraint(OLD)
