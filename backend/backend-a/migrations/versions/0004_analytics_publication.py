"""Managed analytics staging and atomic snapshot publication.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None
MARTS = (
    "analytics_daily",
    "analytics_product_daily",
    "analytics_product_voc_daily",
    "analytics_product_risk",
)


def backup_sqlite_marts():
    if op.get_bind().dialect.name == "sqlite":
        # FK enforcement remains enabled. Preserve children inside this same
        # transaction while Alembic rebuilds their referenced parent table.
        for table in MARTS:
            op.execute(f"CREATE TEMP TABLE _csflow_backup_{table} AS SELECT * FROM {table}")
            op.execute(f"DELETE FROM {table}")


def restore_sqlite_marts():
    if op.get_bind().dialect.name == "sqlite":
        for table in MARTS:
            op.execute(f"INSERT INTO {table} SELECT * FROM _csflow_backup_{table}")
            op.execute(f"DROP TABLE _csflow_backup_{table}")


def upgrade():
    backup_sqlite_marts()
    # Legacy publication has no receipt/hash evidence. Retain all data, but never
    # silently bless it as a managed snapshot. Explicit re-ingestion uses a new ID.
    op.execute("UPDATE analytics_batches SET is_current=false WHERE is_current")
    with op.batch_alter_table("analytics_batches") as b:
        b.add_column(
            sa.Column("validation_passed", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        b.add_column(sa.Column("validated_at", sa.DateTime(timezone=True)))
        b.add_column(sa.Column("content_hash", sa.String(64)))
        b.drop_constraint(op.f("ck_analytics_batches_current_success"), type_="check")
        b.create_check_constraint(
            op.f("ck_analytics_batches_current_success"),
            "NOT is_current OR (status='SUCCEEDED' AND published_at IS NOT NULL AND validation_passed "
            "AND validated_at IS NOT NULL AND content_hash IS NOT NULL)",
        )
    restore_sqlite_marts()
    op.create_table(
        "analytics_receipts",
        sa.Column("batch_id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column(
            "validation_result", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["analytics_batches.batch_id"],
            name=op.f("fk_analytics_receipts_batch_id_analytics_batches"),
        ),
        sa.PrimaryKeyConstraint("batch_id", name=op.f("pk_analytics_receipts")),
    )
    op.create_table(
        "analytics_publication",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Uuid(as_uuid=False)),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["analytics_receipts.batch_id"],
            name=op.f("fk_analytics_publication_batch_id_analytics_receipts"),
        ),
        sa.CheckConstraint("singleton_id=1", name=op.f("ck_analytics_publication_singleton")),
        sa.PrimaryKeyConstraint("singleton_id", name=op.f("pk_analytics_publication")),
    )
    op.execute("INSERT INTO analytics_publication(singleton_id,batch_id) VALUES (1,NULL)")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION csflow_analytics_mart_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE batch_status text;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            SELECT status INTO batch_status FROM analytics_batches WHERE batch_id=OLD.batch_id FOR SHARE;
            IF batch_status='SUCCEEDED' THEN RAISE EXCEPTION 'PUBLISHED_ANALYTICS_IMMUTABLE'; END IF;
          END IF;
          IF TG_OP <> 'DELETE' THEN
            SELECT status INTO batch_status FROM analytics_batches WHERE batch_id=NEW.batch_id FOR SHARE;
            IF batch_status='SUCCEEDED' THEN RAISE EXCEPTION 'PUBLISHED_ANALYTICS_IMMUTABLE'; END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END $$""")
        for table in MARTS:
            op.execute(
                f"CREATE TRIGGER immutable_published BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION csflow_analytics_mart_immutable()"
            )
        op.execute("""CREATE FUNCTION csflow_analytics_head_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.status='SUCCEEDED' THEN
            IF TG_OP='DELETE' THEN RAISE EXCEPTION 'PUBLISHED_ANALYTICS_IMMUTABLE'; END IF;
            IF (to_jsonb(NEW)-'is_current') IS DISTINCT FROM (to_jsonb(OLD)-'is_current') THEN
              RAISE EXCEPTION 'PUBLISHED_ANALYTICS_IMMUTABLE';
            END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END $$""")
        op.execute(
            "CREATE TRIGGER immutable_published BEFORE UPDATE OR DELETE ON analytics_batches "
            "FOR EACH ROW EXECUTE FUNCTION csflow_analytics_head_immutable()"
        )
        op.execute("""CREATE FUNCTION csflow_analytics_receipt_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM 1 FROM analytics_batches WHERE batch_id=OLD.batch_id FOR SHARE;
          IF TG_OP='DELETE' THEN RAISE EXCEPTION 'ANALYTICS_RECEIPT_IMMUTABLE'; END IF;
          IF NEW.payload IS DISTINCT FROM OLD.payload OR NEW.content_hash IS DISTINCT FROM OLD.content_hash OR
             NEW.batch_id IS DISTINCT FROM OLD.batch_id OR EXISTS(SELECT 1 FROM analytics_batches
             WHERE batch_id=OLD.batch_id AND status='SUCCEEDED') THEN
            RAISE EXCEPTION 'ANALYTICS_RECEIPT_IMMUTABLE';
          END IF;
          RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER immutable_receipt BEFORE UPDATE OR DELETE ON analytics_receipts "
            "FOR EACH ROW EXECUTE FUNCTION csflow_analytics_receipt_immutable()"
        )


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Offline downgrade cannot verify analytics history")
    if op.get_bind().execute(sa.text("SELECT 1 FROM analytics_receipts LIMIT 1")).first():
        raise RuntimeError("Downgrade would lose analytics history; retain 0004")
    backup_sqlite_marts()
    if op.get_bind().dialect.name == "postgresql":
        for table in MARTS:
            op.execute(f"DROP TRIGGER immutable_published ON {table}")
        op.execute("DROP TRIGGER immutable_published ON analytics_batches")
        op.execute("DROP TRIGGER immutable_receipt ON analytics_receipts")
        for name in ("mart", "head", "receipt"):
            op.execute(f"DROP FUNCTION csflow_analytics_{name}_immutable()")
    op.drop_table("analytics_publication")
    op.drop_table("analytics_receipts")
    with op.batch_alter_table("analytics_batches") as b:
        b.drop_constraint(op.f("ck_analytics_batches_current_success"), type_="check")
        b.create_check_constraint(
            op.f("ck_analytics_batches_current_success"),
            "NOT is_current OR (status='SUCCEEDED' AND published_at IS NOT NULL)",
        )
        for name in ("validation_passed", "validated_at", "content_hash"):
            b.drop_column(name)
    restore_sqlite_marts()
