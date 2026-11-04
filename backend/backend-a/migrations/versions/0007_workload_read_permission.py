"""Allow explicit workload reads; grant no permissions and change no business rows.

Revision ID: 0007; Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

OLD = (
    "'EXCEPTION_QUEUE_READ','UNROUTED_QUEUE_READ','AUTOMATION_READ',"
    "'AUTOMATION_STOP','AUTOMATION_RESUME','RETENTION_TEAM_REVIEW','RETENTION_GLOBAL_REVIEW'"
)


def constraint(values):
    with op.batch_alter_table("staff_permissions") as batch:
        batch.drop_constraint(op.f("ck_staff_permissions_permission"), type_="check")
        batch.create_check_constraint(op.f("ck_staff_permissions_permission"), f"permission IN ({values})")


def upgrade():
    constraint(OLD + ",'WORKLOAD_READ'")


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify workload authorization/history")
    c = op.get_bind()
    if (
        c.execute(sa.text("SELECT 1 FROM staff_permissions WHERE permission='WORKLOAD_READ' LIMIT 1")).first()
        or c.execute(sa.text("SELECT 1 FROM audit_events WHERE action='READ_WORKLOAD' LIMIT 1")).first()
    ):
        raise RuntimeError("Downgrade would lose workload authorization/history; retain 0007")
    constraint(OLD)
