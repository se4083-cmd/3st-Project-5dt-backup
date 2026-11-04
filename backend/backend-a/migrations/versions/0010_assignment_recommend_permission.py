"""Allow explicit read-only recommendations. No grants or business writes.
Revision ID: 0010; Revises: 0009.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None
OLD = "'EXCEPTION_QUEUE_READ','UNROUTED_QUEUE_READ','AUTOMATION_READ','AUTOMATION_STOP','AUTOMATION_RESUME','RETENTION_TEAM_REVIEW','RETENTION_GLOBAL_REVIEW','WORKLOAD_READ','VOC_IMPROVEMENT_MANAGE','QUALITY_SAMPLE_MANAGE','QUALITY_REVIEW','QUALITY_METRICS_READ','QUALITY_UNATTRIBUTED_MANAGE'"


def permission(values):
    with op.batch_alter_table("staff_permissions") as b:
        b.drop_constraint(op.f("ck_staff_permissions_permission"), type_="check")
        b.create_check_constraint(op.f("ck_staff_permissions_permission"), f"permission IN ({values})")


def upgrade():
    permission(OLD + ",'ASSIGNMENT_RECOMMEND'")


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify recommendation authorization/history")
    c = op.get_bind()
    if (
        c.execute(
            sa.text("SELECT 1 FROM staff_permissions WHERE permission='ASSIGNMENT_RECOMMEND' LIMIT 1")
        ).first()
        or c.execute(
            sa.text("SELECT 1 FROM audit_events WHERE action='READ_ASSIGNMENT_RECOMMENDATIONS' LIMIT 1")
        ).first()
    ):
        raise RuntimeError("Downgrade would lose recommendation authorization/history; retain 0010")
    permission(OLD)
