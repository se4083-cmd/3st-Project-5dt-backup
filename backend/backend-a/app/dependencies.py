from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import auth, repository
from app.db import utcnow
from app.errors import APIError

bearer = HTTPBearer(auto_error=False)


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


DB = Annotated[Session, Depends(get_session, scope="function")]


def current_user(
    request: Request,
    session: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise APIError(401, "AUTHENTICATION_REQUIRED")
    user_id = auth.token_subject(credentials.credentials, request.app.state.settings)
    user = repository.get_user(session, user_id)
    if (
        not user
        or not user["active"]
        or (request.app.state.settings.app_env == "production" and user["is_dev_account"])
    ):
        raise APIError(401, "INVALID_CREDENTIALS", user_id if user else None, "AUTH")
    return user


User = Annotated[dict, Depends(current_user)]


def get_snapshot_session(request: Request):
    engine = request.app.state.engine
    # Establish repeatable-read BEFORE authentication performs its first SELECT.
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with Session(bind=connection) as session:
            try:
                session.info["snapshot_as_of"] = (
                    session.scalar(text("SELECT transaction_timestamp()"))
                    if engine.dialect.name == "postgresql"
                    else utcnow()
                )
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise


SnapshotDB = Annotated[Session, Depends(get_snapshot_session, scope="function")]


def snapshot_user(
    request: Request,
    session: SnapshotDB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    return current_user(request, session, credentials)


SnapshotUser = Annotated[dict, Depends(snapshot_user)]
