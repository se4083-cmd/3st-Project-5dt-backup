from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app import voc_improvements as service
from app.dependencies import DB, SnapshotDB, SnapshotUser, User
from app.followup_schemas import FollowupStatus
from app.routers import Cursor, IdempotencyKey, Limit
from app.schemas import Page
from app.voc_schemas import (
    ImprovementCreate,
    ImprovementDetail,
    ImprovementReceipt,
    ImprovementView,
    PlanCreate,
    TicketLink,
)

router = APIRouter(prefix="/api/v1/staff/voc-improvements", tags=["VOC improvements"])


def command_response(response, result, replay):
    response.status_code = 200 if replay else 201
    response.headers["Idempotency-Replayed"] = str(replay).lower()
    response.headers["Location"] = f"/api/v1/staff/voc-improvements/{result['action_id']}"
    return result


@router.post(
    "",
    response_model=ImprovementReceipt,
    status_code=201,
    responses={200: {"model": ImprovementReceipt, "description": "Idempotent replay"}},
)
def create(
    body: ImprovementCreate,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: IdempotencyKey,
    request: Request,
):
    """ADMIN + VOC_IMPROVEMENT_MANAGE + current team scope. Atomic product
    followup/profile/initial plan; Idempotency-Key replay rechecks authorization.
    """
    result, replay = service.create(session, user, body, idempotency_key, request.app.state.settings)
    return command_response(response, result, replay)


@router.get("", response_model=Page[ImprovementView])
def listing(
    session: SnapshotDB,
    user: SnapshotUser,
    limit: Limit = 20,
    cursor: Cursor = None,
    product_id: UUID | None = None,
    status: FollowupStatus | None = None,
):
    """ADMIN + VOC_IMPROVEMENT_MANAGE. Current authorized owner teams only;
    stable bounded pages, historical comparison scopes independently checked.
    """
    return service.list_improvements(
        session, user, limit, cursor, product_id=str(product_id) if product_id else None, status=status
    )


@router.get("/{action_id}", response_model=ImprovementDetail)
def detail(
    action_id: UUID,
    session: SnapshotDB,
    user: SnapshotUser,
    plan_limit: Limit = 20,
    plan_before_revision: Annotated[int | None, Query(ge=1)] = None,
    ticket_limit: Limit = 20,
    ticket_cursor: Cursor = None,
):
    """ADMIN + VOC_IMPROVEMENT_MANAGE + current owner team scope. Separate
    bounded plan/ticket pages; hidden links are not counted. Fabric effect
    integration is not implemented: UNAVAILABLE, metrics=null even after DONE.
    """
    return service.detail(
        session,
        user,
        str(action_id),
        plan_limit=plan_limit,
        plan_before_revision=plan_before_revision,
        ticket_limit=ticket_limit,
        ticket_cursor=ticket_cursor,
    )


@router.post(
    "/{action_id}/plans",
    response_model=ImprovementReceipt,
    status_code=201,
    responses={200: {"model": ImprovementReceipt, "description": "Idempotent replay"}},
)
def plans(
    action_id: UUID,
    body: PlanCreate,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: IdempotencyKey,
    request: Request,
):
    """ADMIN + VOC_IMPROVEMENT_MANAGE. Append a full plan snapshot using both
    expected revisions. Terminal actions require correction=true and a reason;
    only implementation time/windows can be corrected without reopening work.
    """
    result, replay = service.add_plan(
        session, user, str(action_id), body, idempotency_key, request.app.state.settings
    )
    return command_response(response, result, replay)


@router.post(
    "/{action_id}/tickets",
    response_model=ImprovementReceipt,
    status_code=201,
    responses={200: {"model": ImprovementReceipt, "description": "Idempotent replay"}},
)
def tickets(
    action_id: UUID,
    body: TicketLink,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: IdempotencyKey,
):
    """ADMIN + VOC_IMPROVEMENT_MANAGE. Check current action AND ticket scope,
    known matching product, both revisions and Idempotency-Key on every command.
    """
    result, replay = service.link_ticket(session, user, str(action_id), body, idempotency_key)
    return command_response(response, result, replay)
