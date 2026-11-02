from alembic import context

from app.config import get_settings
from app.db import UTCDateTime, build_engine
from app.schema import metadata


def render_item(kind, obj, autogen_context):
    if kind == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run():
    if context.is_offline_mode():
        context.configure(
            url=get_settings().database_url,
            target_metadata=metadata,
            literal_binds=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = build_engine(get_settings())
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=metadata,
                compare_type=True,
                render_item=render_item,
                # build_engine issues real BEGIN IMMEDIATE for SQLite, so DDL is
                # transactional too. Keep multi-revision downgrade all-or-nothing.
                transactional_ddl=True,
            )
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


run()
