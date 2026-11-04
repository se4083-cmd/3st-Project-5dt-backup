from datetime import timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import AwareDatetime
from sqlalchemy import select

from app import quality_metrics
from app import quality_service as service
from app.dependencies import DB, SnapshotDB, SnapshotUser, User
from app.errors import APIError
from app.quality_models import rubrics
from app.quality_schemas import (
    Candidate,
    HistoryPage,
    Material,
    MaterialRequest,
    Origin,
    QualityMetrics,
    Reassign,
    Receipt,
    ReviewCreate,
    RubricView,
    SampleCreate,
    SampleView,
    VoidSample,
)
from app.routers import Cursor, IdempotencyKey, Limit
from app.schemas import Page

router = APIRouter(prefix="/api/v1/staff/quality", tags=["manual quality review"])


def respond(response, result, replay):
    response.status_code = 200 if replay else 201
    response.headers["Idempotency-Replayed"] = str(replay).lower()
    return result


@router.get("/rubrics", response_model=list[RubricView])
def catalog(session: SnapshotDB, user: SnapshotUser):
    """Development proposal criteria; this is not an agreed operational rubric."""
    g = service.grants(session, user)
    if not (
        {"QUALITY_REVIEW"} & g
        or user["role"] == "ADMIN"
        and {"QUALITY_SAMPLE_MANAGE", "QUALITY_METRICS_READ"} & g
    ):
        raise APIError(403, "EXPLICIT_PERMISSION_REQUIRED", user["user_id"])
    return [dict(r) for r in session.execute(select(rubrics).order_by(rubrics.c.version)).mappings()]


@router.get("/candidates", response_model=Page[Candidate])
def candidates(
    session: SnapshotDB,
    user: SnapshotUser,
    origin: Origin = "APPLICATION",
    unattributed: bool = False,
    limit: Limit = 20,
    cursor: Cursor = None,
):
    """ADMIN + QUALITY_SAMPLE_MANAGE; unattributed requires separate explicit permission."""
    return service.candidate_list(session, user, limit, cursor, origin=origin, unattributed=unattributed)


@router.post(
    "/samples",
    response_model=Receipt,
    status_code=201,
    responses={200: {"model": Receipt, "description": "Idempotent replay"}},
)
def create(body: SampleCreate, session: DB, user: User, response: Response, idempotency_key: IdempotencyKey):
    """ADMIN + QUALITY_SAMPLE_MANAGE + current team scope. One official message/rubric sample."""
    result, replay = service.create_sample(session, user, body, idempotency_key)
    return respond(response, result, replay)


@router.get("/samples", response_model=Page[SampleView])
def samples(session: SnapshotDB, user: SnapshotUser, limit: Limit = 20, cursor: Cursor = None):
    return service.sample_list(session, user, limit, cursor)


@router.post("/samples/{sample_id}/material", response_model=Material)
def material(sample_id: UUID, body: MaterialRequest, session: SnapshotDB, user: SnapshotUser):
    """QUALITY_REVIEW + assigned reviewer + current review team only. No general ticket access."""
    return service.material(session, user, str(sample_id), body.purpose_code)


@router.post(
    "/samples/{sample_id}/reviews",
    response_model=Receipt,
    status_code=201,
    responses={200: {"model": Receipt, "description": "Idempotent replay"}},
)
def review(
    sample_id: UUID,
    body: ReviewCreate,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: IdempotencyKey,
):
    result, replay = service.mutate(session, user, str(sample_id), body, idempotency_key, "REVIEW")
    return respond(response, result, replay)


@router.post(
    "/samples/{sample_id}/assignment",
    response_model=Receipt,
    status_code=201,
    responses={200: {"model": Receipt, "description": "Idempotent replay"}},
)
def reassign(
    sample_id: UUID,
    body: Reassign,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: IdempotencyKey,
):
    result, replay = service.mutate(session, user, str(sample_id), body, idempotency_key, "REASSIGN")
    return respond(response, result, replay)


@router.post(
    "/samples/{sample_id}/void",
    response_model=Receipt,
    status_code=201,
    responses={200: {"model": Receipt, "description": "Idempotent replay"}},
)
def void(
    sample_id: UUID,
    body: VoidSample,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: IdempotencyKey,
):
    result, replay = service.mutate(session, user, str(sample_id), body, idempotency_key, "VOID")
    return respond(response, result, replay)


@router.get("/samples/{sample_id}/history", response_model=HistoryPage)
def history(
    sample_id: UUID,
    session: SnapshotDB,
    user: SnapshotUser,
    limit: Limit = 20,
    before_revision: Annotated[int | None, Query(ge=1)] = None,
):
    return service.history(session, user, str(sample_id), limit, before_revision)


@router.get("/metrics", response_model=QualityMetrics)
def metrics(
    session: SnapshotDB,
    user: SnapshotUser,
    request: Request,
    response_start: AwareDatetime,
    response_end: AwareDatetime,
    rubric_version: str = "DEV_QUALITY_V1",
    origin: Origin = "APPLICATION",
    team_ids: Annotated[list[UUID] | None, Query(max_length=64)] = None,
    include_unattributed: bool = False,
):
    """ADMIN + QUALITY_METRICS_READ; response committed-at cohort, current snapshot only.
    Manual-sample accuracy is not a population estimate. Synthetic origin is separate.
    """
    if "as_of" in request.query_params:
        raise APIError(422, "QUALITY_CURRENT_SNAPSHOT_ONLY")
    return quality_metrics.metrics(
        session,
        user,
        response_start.astimezone(timezone.utc),
        response_end.astimezone(timezone.utc),
        rubric_version,
        origin,
        team_ids,
        include_unattributed,
    )
