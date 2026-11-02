"""Staff exception routing/capabilities and durable automation generation fence.
Revision ID: 0005; Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "automation_jobs",
        sa.Column("automation_generation", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
    )
    op.create_table(
        "staff_permissions",
        sa.Column("user_id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("permission", sa.String(64), primary_key=True),
        sa.Column("granted_by", sa.Uuid(as_uuid=False)),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.ForeignKeyConstraint(["granted_by"], ["users.user_id"]),
        sa.CheckConstraint(
            "permission IN ('EXCEPTION_QUEUE_READ','UNROUTED_QUEUE_READ','AUTOMATION_READ','AUTOMATION_STOP','AUTOMATION_RESUME')",
            name=op.f("ck_staff_permissions_permission"),
        ),
    )
    op.create_table(
        "queue_routes",
        sa.Column("ticket_id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("cycle_no", sa.BigInteger(), primary_key=True),
        sa.Column("team_id", sa.Uuid(as_uuid=False)),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("recorded_by_service", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.team_id"]),
        sa.CheckConstraint("cycle_no>=1 AND revision>=1", name=op.f("ck_queue_routes_revision")),
    )
    op.create_table(
        "automation_control",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("changed_by", sa.Uuid(as_uuid=False)),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.user_id"]),
        sa.CheckConstraint(
            "singleton_id=1 AND revision>=1 AND generation>=1", name=op.f("ck_automation_control_singleton")
        ),
        sa.CheckConstraint(
            "reason_code IN ('INITIAL_STATE','SAFETY_INCIDENT','OPERATOR_PAUSE','VERIFICATION_COMPLETE','INCIDENT_RESOLVED')",
            name=op.f("ck_automation_control_reason"),
        ),
    )
    op.create_table(
        "automation_control_history",
        sa.Column("revision", sa.BigInteger(), primary_key=True),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("changed_by", sa.Uuid(as_uuid=False)),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.user_id"]),
        sa.CheckConstraint(
            "revision>=1 AND generation>=1", name=op.f("ck_automation_control_history_revision")
        ),
        sa.CheckConstraint(
            "reason_code IN ('INITIAL_STATE','SAFETY_INCIDENT','OPERATOR_PAUSE','VERIFICATION_COMPLETE','INCIDENT_RESOLVED')",
            name=op.f("ck_automation_control_history_reason"),
        ),
    )
    op.execute(
        "INSERT INTO automation_control(singleton_id,paused,revision,generation,reason_code,changed_at) VALUES(1,false,1,1,'INITIAL_STATE',CURRENT_TIMESTAMP)"
    )
    op.execute(
        "INSERT INTO automation_control_history(revision,generation,paused,reason_code,changed_at) VALUES(1,1,false,'INITIAL_STATE',CURRENT_TIMESTAMP)"
    )
    # Deliberately no grants, routing backfill or policy/rule activation.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION csflow_control_history_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'CONTROL_HISTORY_IMMUTABLE'; END $$""")
        op.execute(
            "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON automation_control_history FOR EACH ROW EXECUTE FUNCTION csflow_control_history_immutable()"
        )


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify staff/control history")
    c = op.get_bind()
    if any(
        c.execute(sa.text(sql)).first()
        for sql in [
            "SELECT 1 FROM staff_permissions LIMIT 1",
            "SELECT 1 FROM queue_routes LIMIT 1",
            "SELECT 1 FROM automation_control_history WHERE revision>1 LIMIT 1",
            "SELECT 1 FROM audit_events WHERE action='READ_STAFF_TICKET' LIMIT 1",
        ]
    ):
        raise RuntimeError("Downgrade would lose staff/control history; retain 0005")
    if c.dialect.name == "postgresql":
        op.execute("DROP TRIGGER immutable_history ON automation_control_history")
        op.execute("DROP FUNCTION csflow_control_history_immutable()")
    for table in ("automation_control_history", "automation_control", "queue_routes", "staff_permissions"):
        op.drop_table(table)
    # Supported SQLite/PostgreSQL versions can drop this unindexed scalar column
    # without rebuilding the referenced job table or losing historical rows.
    op.drop_column("automation_jobs", "automation_generation")
