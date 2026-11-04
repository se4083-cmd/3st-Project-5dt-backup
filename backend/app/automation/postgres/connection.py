"""Backend B PostgreSQL connection using Backend A shared infrastructure."""

from app.config import get_settings
from app.db import build_engine, session_factory


def create_session_factory():
    """Create a session factory for Backend A's shared PostgreSQL database."""
    settings = get_settings()

    engine = build_engine(settings)

    if engine.dialect.name != "postgresql":
        engine.dispose()
        raise RuntimeError("Backend B worker requires PostgreSQL")

    return session_factory(engine)
