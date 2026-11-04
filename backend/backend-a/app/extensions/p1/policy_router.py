import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.dependencies import DB, User
from app.errors import APIError
from app.routers import Cursor, Limit

from . import policy_service as service
from .policy_schemas import (
    AppendVersion,
    ComparePolicy,
    ComparisonPage,
    ComparisonView,
    PolicyDecision,
    PolicyPage,
    PolicyVersion,
    PolicyView,
    RegisterPolicy,
    VersionPage,
)
from .settings import enabled
from .voc_router import Key


class PolicySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="P1_POLICY_", extra="ignore", hide_input_in_errors=True)
    enabled: bool = False


def policy_enabled():
    from pydantic import ValidationError

    try:
        active = PolicySettings(_env_file=os.environ.get("CSFLOW_ENV_FILE", ".env")).enabled
    except ValidationError:
        raise APIError(503, "POLICY_CONFIGURATION_INVALID") from None
    if not active:
        raise APIError(503, "POLICY_DISABLED")


router = APIRouter(
    prefix="/api/v1/admin/p1",
    tags=["P1 policy review"],
    dependencies=[Depends(enabled), Depends(policy_enabled)],
)


def reply(response, result, replay, created=True):
    response.headers["Idempotency-Replayed"] = str(replay).lower()
    if created and replay:
        response.status_code = 200
    return result


@router.post("/policies", response_model=PolicyView, status_code=201, responses={200: {"model": PolicyView}})
def register(body: RegisterPolicy, session: DB, user: User, response: Response, idempotency_key: Key):
    result, replay = service.register(session, user, body, idempotency_key)
    return reply(response, result, replay)


@router.get("/policies", response_model=PolicyPage)
def history(session: DB, user: User, limit: Limit = 20, cursor: Cursor = None):
    return service.history(session, user, limit, cursor)


@router.get("/policies/{policy_id}", response_model=PolicyView)
def detail(policy_id: UUID, session: DB, user: User):
    return service.detail(session, user, str(policy_id))


@router.post(
    "/policies/{policy_id}/versions",
    response_model=PolicyVersion,
    status_code=201,
    responses={200: {"model": PolicyVersion}},
)
def append(
    policy_id: UUID, body: AppendVersion, session: DB, user: User, response: Response, idempotency_key: Key
):
    result, replay = service.append(session, user, str(policy_id), body, idempotency_key)
    return reply(response, result, replay)


@router.get("/policies/{policy_id}/versions", response_model=VersionPage)
def versions(
    policy_id: UUID,
    session: DB,
    user: User,
    limit: Limit = 20,
    before_version: Annotated[int | None, Query(ge=1)] = None,
):
    return service.version_page(session, user, str(policy_id), limit, before_version)


@router.get("/policies/{policy_id}/versions/{version_id}", response_model=PolicyVersion)
def version(policy_id: UUID, version_id: UUID, session: DB, user: User):
    return service.version_detail(session, user, str(policy_id), str(version_id))


@router.post(
    "/policies/{policy_id}/comparisons",
    response_model=ComparisonView,
    status_code=201,
    responses={200: {"model": ComparisonView}},
)
def compare(
    policy_id: UUID, body: ComparePolicy, session: DB, user: User, response: Response, idempotency_key: Key
):
    result, replay = service.compare(session, user, str(policy_id), body, idempotency_key)
    return reply(response, result, replay)


@router.get("/policies/{policy_id}/comparisons", response_model=ComparisonPage)
def comparisons(policy_id: UUID, session: DB, user: User, limit: Limit = 20, cursor: Cursor = None):
    return service.comparison_history(session, user, str(policy_id), limit, cursor)


@router.get("/policy-comparisons/{comparison_id}", response_model=ComparisonView)
def comparison(comparison_id: UUID, session: DB, user: User):
    return service.comparison_detail(session, user, str(comparison_id))


@router.post("/policy-comparisons/{comparison_id}/reviews", response_model=ComparisonView)
def review(
    comparison_id: UUID,
    body: PolicyDecision,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: Key,
):
    result, replay = service.review(session, user, str(comparison_id), body, idempotency_key)
    return reply(response, result, replay, False)
