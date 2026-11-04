from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import ValidationError

from app.dependencies import DB, User
from app.errors import APIError
from app.routers import Cursor, Limit

from . import voc_provider, voc_service
from .settings import enabled
from .voc_schemas import GenerateVOC, ReviewVOC, VOCPage, VOCView


def voc_enabled():
    try:
        config = voc_provider.settings()
    except ValidationError:
        raise APIError(503, "VOC_CONFIGURATION_INVALID") from None
    if not config.enabled:
        raise APIError(503, "VOC_DISABLED")
    return config


Config = Annotated[voc_provider.VOCSettings, Depends(voc_enabled)]
Key = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
]
router = APIRouter(
    prefix="/api/v1/admin/p1/voc-proposals",
    tags=["P1 VOC proposals"],
    dependencies=[Depends(enabled), Depends(voc_enabled)],
)


@router.post("", response_model=VOCView, status_code=201, responses={200: {"model": VOCView}})
def generate(
    body: GenerateVOC,
    session: DB,
    user: User,
    request: Request,
    response: Response,
    config: Config,
    idempotency_key: Key,
):
    result, replay = voc_service.generate(
        session, user, body, idempotency_key, request.app.state.settings, config
    )
    response.headers["Idempotency-Replayed"] = str(replay).lower()
    response.headers["Location"] = f"/api/v1/admin/p1/voc-proposals/{result['request_id']}"
    if replay:
        response.status_code = 200
    return result


@router.get("", response_model=VOCPage)
def history(
    session: DB, user: User, limit: Limit = 20, cursor: Cursor = None, product_id: UUID | None = None
):
    return voc_service.history(session, user, limit, cursor, product_id)


@router.get("/{request_id}", response_model=VOCView)
def detail(request_id: UUID, session: DB, user: User):
    return voc_service.detail(session, user, str(request_id))


@router.post("/{request_id}/reviews", response_model=VOCView)
def review(
    request_id: UUID, body: ReviewVOC, session: DB, user: User, response: Response, idempotency_key: Key
):
    result, replay = voc_service.review(session, user, str(request_id), body, idempotency_key)
    response.headers["Idempotency-Replayed"] = str(replay).lower()
    return result
