from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import SnapshotDB, SnapshotUser
from app.errors import APIError
from app.routers import Cursor, Limit

from . import monitoring_service as service
from .permissions import require_monitor, ui_session
from .schemas import AiCallSummary, JobPage, MonitorSummary, P1Session, Unobserved
from .settings import enabled

router = APIRouter(prefix="/api/v1/admin/p1", tags=["P1 monitoring"], dependencies=[Depends(enabled)])
Teams = Annotated[list[UUID] | None, Query(max_length=100)]
Kind = Literal["AUTO", "HANDOFF"]
Status = Literal["PENDING", "RUNNING", "RETRY", "SUCCEEDED", "FAILED", "HANDED_OFF", "CANCELLED"]


@router.get("/session", response_model=P1Session)
def session_bridge(session: SnapshotDB, user: SnapshotUser):
    return ui_session(session, user)


@router.get("/monitoring/summary", response_model=MonitorSummary)
def summary(
    request: Request,
    session: SnapshotDB,
    user: SnapshotUser,
    team_ids: Teams = None,
    job_kind: Kind | None = None,
):
    selected = require_monitor(session, user, team_ids)
    return service.summary(session, user, request.app.state.settings, selected, job_kind)


@router.get("/monitoring/jobs", response_model=JobPage)
def jobs(
    session: SnapshotDB,
    user: SnapshotUser,
    team_ids: Teams = None,
    job_kind: Kind | None = None,
    status: Status | None = None,
    limit: Limit = 20,
    cursor: Cursor = None,
):
    selected = require_monitor(session, user, team_ids)
    return service.job_page(
        session, user, selected, job_kind=job_kind, status=status, limit=limit, cursor=cursor
    )


@router.get("/monitoring/ai-calls", response_model=AiCallSummary)
def ai_calls(
    session: SnapshotDB,
    user: SnapshotUser,
    team_ids: Teams = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
):
    selected = require_monitor(session, user, team_ids)
    end = to or session.info["snapshot_as_of"]
    start = from_ or end - timedelta(days=1)
    if any(t.tzinfo is None or t.utcoffset() is None for t in (start, end)):
        raise APIError(422, "TIMEZONE_REQUIRED")
    if not timedelta(0) < end - start <= timedelta(days=7):
        raise APIError(422, "INVALID_OBSERVATION_WINDOW")
    return dict(
        Unobserved().model_dump(),
        **{"from": start.astimezone(timezone.utc), "to": end.astimezone(timezone.utc)},
        as_of=session.info["snapshot_as_of"],
        selected_team_ids=selected,
        attempt_count=None,
        failed_attempt_count=None,
        retry_attempt_count=None,
        error_rate=None,
        counts_by_code=None,
        started_count=None,
        unknown_count=None,
        sources={"MOCK": None, "AZURE_OPENAI": None},
    )
