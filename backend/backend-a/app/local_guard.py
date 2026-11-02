"""Opt-in local execution fence; validates without DNS or network requests."""

import re

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def require_local_database(value, *, postgres_only=False):
    try:
        url = make_url(value)
        if not postgres_only and url.drivername == "sqlite+pysqlite":
            if url.query or (url.database or "").startswith(("//", "\\\\", "file:")):
                raise ValueError()
            return url
        if url.drivername != "postgresql+psycopg" or url.host != "127.0.0.1":
            raise ValueError()
        if (
            not url.port
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", url.database or "")
            or any(k not in {"sslmode", "options", "connect_timeout", "application_name"} for k in url.query)
        ):
            raise ValueError()
        if url.query.get("sslmode", "disable") != "disable":
            raise ValueError()
        return url
    except (ArgumentError, ValueError, TypeError):
        # Never include the rejected URI (which can contain a password).
        raise ValueError("LOCAL_DATABASE_REQUIRED") from None
