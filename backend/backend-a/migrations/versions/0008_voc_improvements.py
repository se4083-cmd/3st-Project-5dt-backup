"""VOC product improvement profiles, immutable plans and private command receipts.

Revision ID: 0008; Revises: 0007. No existing business rows or grants changed.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

OLD = "'EXCEPTION_QUEUE_READ','UNROUTED_QUEUE_READ','AUTOMATION_READ','AUTOMATION_STOP','AUTOMATION_RESUME','RETENTION_TEAM_REVIEW','RETENTION_GLOBAL_REVIEW','WORKLOAD_READ'"


def permission(values):
    with op.batch_alter_table("staff_permissions") as b:
        b.drop_constraint(op.f("ck_staff_permissions_permission"), type_="check")
        b.create_check_constraint(op.f("ck_staff_permissions_permission"), f"permission IN ({values})")


def upgrade():
    permission(OLD + ",'VOC_IMPROVEMENT_MANAGE'")
    profiles = op.create_table(
        "voc_improvement_profiles",
        Column("action_id", Uuid(as_uuid=False), ForeignKey("followup_actions.action_id"), primary_key=True),
        Column("product_id", Uuid(as_uuid=False), ForeignKey("products.product_id"), nullable=False),
        Column("current_plan_revision", BigInteger(), nullable=False),
        Column("created_by", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
        Column("created_at", sa.DateTime(timezone=True), nullable=False),
        CheckConstraint("current_plan_revision>=1", name="revision"),
    )
    op.create_index("ix_voc_profiles_product", "voc_improvement_profiles", ["product_id", "action_id"])

    plans = op.create_table(
        "voc_improvement_plan_revisions",
        Column("action_id", Uuid(as_uuid=False), ForeignKey(profiles.c.action_id), primary_key=True),
        Column("revision", BigInteger(), primary_key=True),
        Column("issue_code", String(64), nullable=False),
        Column("improvement_text", Text(), nullable=False),
        Column("implemented_at", sa.DateTime(timezone=True)),
        Column("before_start", sa.DateTime(timezone=True)),
        Column("before_end", sa.DateTime(timezone=True)),
        Column("after_start", sa.DateTime(timezone=True)),
        Column("after_end", sa.DateTime(timezone=True)),
        Column("owner_team_id_snapshot", Uuid(as_uuid=False), ForeignKey("teams.team_id"), nullable=False),
        Column("source_batch_id", Uuid(as_uuid=False), ForeignKey("analytics_batches.batch_id")),
        Column("source_scope_key", String(64)),
        Column("change_kind", String(16), nullable=False),
        Column("change_reason", String(1000), nullable=False),
        Column("created_by", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
        Column("created_at", sa.DateTime(timezone=True), nullable=False),
        CheckConstraint("revision>=1", name="revision"),
        CheckConstraint("implemented_at IS NULL OR implemented_at<=created_at", name="implementation_time"),
        CheckConstraint(
            "issue_code IN ('DELIVERY_DELAY','RETURN_PROCESS','REFUND_DELAY','DAMAGED','PAYMENT_ERROR','ACCOUNT_ERROR')",
            name="issue",
        ),
        CheckConstraint(
            "length(trim(improvement_text)) BETWEEN 1 AND 4000 AND length(trim(change_reason)) BETWEEN 1 AND 1000",
            name="text",
        ),
        CheckConstraint("change_kind IN ('INITIAL','PLAN','CORRECTION')", name="change_kind"),
        CheckConstraint("(source_batch_id IS NULL) = (source_scope_key IS NULL)", name="source_pair"),
        CheckConstraint(
            "(before_start IS NULL AND before_end IS NULL AND after_start IS NULL AND after_end IS NULL) OR "
            "(before_start IS NOT NULL AND before_end IS NOT NULL AND after_start IS NOT NULL AND after_end IS NOT NULL "
            "AND implemented_at IS NOT NULL AND before_start<before_end AND after_start<after_end "
            "AND before_end<=implemented_at AND implemented_at<=after_start "
            "AND before_end-before_start=after_end-after_start)",
            name="windows",
        ),
    )
    op.create_index("ix_voc_plans_source_batch", "voc_improvement_plan_revisions", ["source_batch_id"])
    op.create_table(
        "voc_improvement_plan_teams",
        Column("action_id", Uuid(as_uuid=False), primary_key=True),
        Column("revision", BigInteger(), primary_key=True),
        Column("team_id", Uuid(as_uuid=False), ForeignKey("teams.team_id"), primary_key=True),
        ForeignKeyConstraint(["action_id", "revision"], [plans.c.action_id, plans.c.revision]),
    )
    op.create_index(
        "ix_voc_plan_teams_team", "voc_improvement_plan_teams", ["team_id", "action_id", "revision"]
    )
    op.create_table(
        "voc_improvement_ticket_links",
        Column("action_id", Uuid(as_uuid=False), ForeignKey(profiles.c.action_id), primary_key=True),
        Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id"), primary_key=True),
        Column("linked_by", Uuid(as_uuid=False), ForeignKey("users.user_id"), nullable=False),
        Column("linked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_voc_ticket_links_ticket", "voc_improvement_ticket_links", ["ticket_id", "action_id"])
    op.create_table(
        "voc_improvement_receipts",
        Column("user_id", Uuid(as_uuid=False), ForeignKey("users.user_id"), primary_key=True),
        Column("key", String(128), primary_key=True),
        Column("operation", String(16), nullable=False),
        Column("request_hash", String(64), nullable=False),
        Column("action_id", Uuid(as_uuid=False), ForeignKey(profiles.c.action_id), nullable=False),
        Column("plan_revision", BigInteger(), nullable=False),
        Column("ticket_id", Uuid(as_uuid=False), ForeignKey("tickets.ticket_id")),
        Column("response_snapshot", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        Column("created_at", sa.DateTime(timezone=True), nullable=False),
        ForeignKeyConstraint(["action_id", "plan_revision"], [plans.c.action_id, plans.c.revision]),
        CheckConstraint("operation IN ('CREATE','PLAN','LINK')", name="operation"),
    )
    op.create_index("ix_voc_receipts_action", "voc_improvement_receipts", ["action_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION csflow_voc_history_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'VOC_HISTORY_IMMUTABLE'; END $$""")
        for table in (
            "voc_improvement_plan_revisions",
            "voc_improvement_plan_teams",
            "voc_improvement_ticket_links",
            "voc_improvement_receipts",
        ):
            op.execute(
                f"CREATE TRIGGER immutable_voc_history BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION csflow_voc_history_immutable()"
            )
        # A plan command writes its membership before its immutable receipt.
        # Once committed, later INSERTs must not silently widen historical scope.
        op.execute("""CREATE FUNCTION csflow_voc_membership_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM 1 FROM voc_improvement_plan_revisions
          WHERE action_id=NEW.action_id AND revision=NEW.revision FOR SHARE;
          IF EXISTS(SELECT 1 FROM voc_improvement_receipts WHERE action_id=NEW.action_id
                    AND plan_revision=NEW.revision AND operation IN ('CREATE','PLAN')) THEN
            RAISE EXCEPTION 'VOC_HISTORY_IMMUTABLE';
          END IF;
          RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER sealed_voc_membership BEFORE INSERT ON voc_improvement_plan_teams "
            "FOR EACH ROW EXECUTE FUNCTION csflow_voc_membership_guard()"
        )
        op.execute("""CREATE FUNCTION csflow_voc_product_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_TABLE_NAME='voc_improvement_profiles' THEN
            IF TG_OP='UPDATE' THEN
              IF (NEW.action_id,NEW.product_id,NEW.created_by,NEW.created_at) IS DISTINCT FROM
                 (OLD.action_id,OLD.product_id,OLD.created_by,OLD.created_at)
                 OR NEW.current_plan_revision<>OLD.current_plan_revision+1 THEN
                RAISE EXCEPTION 'VOC_PROFILE_IDENTITY_IMMUTABLE';
              END IF;
              IF NOT EXISTS(SELECT 1 FROM voc_improvement_plan_revisions
                            WHERE action_id=NEW.action_id AND revision=NEW.current_plan_revision) THEN
                RAISE EXCEPTION 'VOC_PLAN_HEAD_REQUIRED';
              END IF;
            END IF;
            PERFORM 1 FROM followup_actions WHERE action_id=NEW.action_id AND product_id=NEW.product_id
                      AND ticket_id IS NULL AND NOT blocks_resolution FOR SHARE;
            IF NOT FOUND THEN RAISE EXCEPTION 'VOC_PRODUCT_FOLLOWUP_REQUIRED'; END IF;
          ELSE
            IF EXISTS(SELECT 1 FROM voc_improvement_profiles WHERE action_id=OLD.action_id)
               AND ((NEW.ticket_id,NEW.product_id) IS DISTINCT FROM (OLD.ticket_id,OLD.product_id)
                    OR NEW.blocks_resolution) THEN
              RAISE EXCEPTION 'VOC_PRODUCT_FOLLOWUP_REQUIRED';
            END IF;
          END IF;
          RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER voc_product_profile BEFORE INSERT OR UPDATE ON voc_improvement_profiles "
            "FOR EACH ROW EXECUTE FUNCTION csflow_voc_product_guard()"
        )
        op.execute(
            "CREATE TRIGGER voc_product_action BEFORE UPDATE ON followup_actions "
            "FOR EACH ROW EXECUTE FUNCTION csflow_voc_product_guard()"
        )


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify VOC history")
    conn = op.get_bind()
    for table in ("voc_improvement_profiles", "voc_improvement_receipts"):
        if conn.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("Downgrade would lose VOC history; retain 0008")
    if (
        conn.execute(
            sa.text("SELECT 1 FROM staff_permissions WHERE permission='VOC_IMPROVEMENT_MANAGE' LIMIT 1")
        ).first()
        or conn.execute(sa.text("SELECT 1 FROM audit_events WHERE action LIKE 'VOC_%' LIMIT 1")).first()
    ):
        raise RuntimeError("Downgrade would lose VOC authorization/history; retain 0008")
    if conn.dialect.name == "postgresql":
        op.execute("DROP TRIGGER voc_product_action ON followup_actions")
        op.execute("DROP FUNCTION csflow_voc_product_guard() CASCADE")
        op.execute("DROP FUNCTION csflow_voc_history_immutable() CASCADE")
        op.execute("DROP FUNCTION csflow_voc_membership_guard() CASCADE")
    for table in (
        "voc_improvement_receipts",
        "voc_improvement_ticket_links",
        "voc_improvement_plan_teams",
        "voc_improvement_plan_revisions",
        "voc_improvement_profiles",
    ):
        op.drop_table(table)
    permission(OLD)
