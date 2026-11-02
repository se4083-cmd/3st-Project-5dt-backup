import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import Settings


def utcnow():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """PostgreSQL timestamptz; explicit UTC reconstruction for SQLite development."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Naive timestamps are prohibited")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def build_engine(settings: Settings):
    if os.environ.get("CSFLOW_LOCAL_ONLY") == "1":
        from app.local_guard import require_local_database

        require_local_database(settings.database_url)
    kwargs = dict(pool_pre_ping=True, hide_parameters=True, echo=False)
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
    else:
        kwargs.update(
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_timeout=settings.pool_timeout,
            pool_recycle=1800,
            connect_args={
                "connect_timeout": settings.db_connect_timeout,
                "options": make_url(settings.database_url).query.get("options", "")
                + f" -c timezone=UTC -c statement_timeout={settings.db_statement_timeout_ms}",
            },
        )
    engine = create_engine(settings.database_url, **kwargs)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_pragmas(connection, _):
            connection.isolation_level = None
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=15000")

        @event.listens_for(engine, "begin")
        def sqlite_begin(connection):
            # Real outer transactions make nested savepoint rollback reliable.
            # SQLite dev requests serialize writers; PostgreSQL uses row/unique locks.
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
