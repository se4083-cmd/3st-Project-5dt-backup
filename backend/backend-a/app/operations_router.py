from uuid import UUID

from fastapi import APIRouter, Response

from app import customer360, followups
from app.dependencies import DB, SnapshotDB, SnapshotUser, User
from app.followup_schemas import (
    FollowupCancel,
    FollowupCreate,
    FollowupPatch,
    FollowupPublic,
    FollowupReceipt,
    FollowupStaff,
    FollowupState,
    FollowupStatus,
)
from app.routers import Cursor, IdempotencyKey, Limit
from app.schemas import Page

router = APIRouter(prefix="/api/v1")


@router.get("/followups", response_model=Page[FollowupPublic], tags=["public followups"])
def public_list(
    session: DB, user: User, limit: Limit = 20, cursor: Cursor = None, ticket_id: UUID | None = None
):
    return followups.list_actions(
        session, user, limit, cursor, staff=False, ticket_id=str(ticket_id) if ticket_id else None
    )


@router.get("/followups/{action_id}", response_model=FollowupPublic, tags=["public followups"])
def public_detail(action_id: UUID, session: DB, user: User):
    return followups.get(session, user, str(action_id), staff=False)


@router.get("/staff/followups", response_model=Page[FollowupStaff], tags=["staff followups"])
def staff_list(
    session: DB,
    user: User,
    limit: Limit = 20,
    cursor: Cursor = None,
    ticket_id: UUID | None = None,
    product_id: UUID | None = None,
    status: FollowupStatus | None = None,
):
    return followups.list_actions(
        session,
        user,
        limit,
        cursor,
        staff=True,
        ticket_id=str(ticket_id) if ticket_id else None,
        product_id=str(product_id) if product_id else None,
        status=status,
    )


@router.get("/staff/followups/{action_id}", response_model=FollowupStaff, tags=["staff followups"])
def staff_detail(action_id: UUID, session: DB, user: User):
    return followups.get(session, user, str(action_id), staff=True)


@router.post(
    "/staff/followups",
    response_model=FollowupReceipt,
    status_code=201,
    tags=["staff followups"],
    responses={200: {"model": FollowupReceipt, "description": "Idempotent replay"}},
)
def create(
    body: FollowupCreate, session: DB, user: User, response: Response, idempotency_key: IdempotencyKey
):
    result, replay = followups.create(session, user, body, idempotency_key)
    response.status_code = 200 if replay else 201
    response.headers["Idempotency-Replayed"] = str(replay).lower()
    response.headers["Location"] = f"/api/v1/staff/followups/{result['action_id']}"
    return result


@router.patch("/staff/followups/{action_id}", response_model=FollowupStaff, tags=["staff followups"])
def patch(action_id: UUID, body: FollowupPatch, session: DB, user: User):
    return followups.mutate(session, user, str(action_id), body)


@router.post("/staff/followups/{action_id}/status", response_model=FollowupStaff, tags=["staff followups"])
def status(action_id: UUID, body: FollowupState, session: DB, user: User):
    return followups.mutate(session, user, str(action_id), body, state=True)


@router.delete("/staff/followups/{action_id}", response_model=FollowupStaff, tags=["staff followups"])
def cancel(action_id: UUID, body: FollowupCancel, session: DB, user: User):
    return followups.mutate(
        session,
        user,
        str(action_id),
        FollowupState(
            expected_revision=body.expected_revision,
            status="CANCELLED",
            cancellation_reason=body.cancellation_reason,
        ),
        state=True,
    )


@router.post(
    "/staff/customers/{customer_id}/360", response_model=customer360.Customer360, tags=["customer360"]
)
def overview(customer_id: UUID, body: customer360.ViewPurpose, session: SnapshotDB, user: SnapshotUser):
    return customer360.view(session, user, str(customer_id), body)


@router.post(
    "/staff/customers/{customer_id}/360/tickets",
    response_model=Page[customer360.HistoryTicket],
    tags=["customer360"],
)
def history(
    customer_id: UUID,
    body: customer360.ViewPurpose,
    session: SnapshotDB,
    user: SnapshotUser,
    limit: Limit = 20,
    cursor: Cursor = None,
    unresolved_only: bool = False,
):
    return customer360.view(
        session,
        user,
        str(customer_id),
        body,
        kind="tickets",
        limit=limit,
        cursor=cursor,
        unresolved_only=unresolved_only,
    )


@router.post(
    "/staff/customers/{customer_id}/360/followups", response_model=Page[FollowupStaff], tags=["customer360"]
)
def history_followups(
    customer_id: UUID,
    body: customer360.ViewPurpose,
    session: SnapshotDB,
    user: SnapshotUser,
    limit: Limit = 20,
    cursor: Cursor = None,
):
    return customer360.view(
        session, user, str(customer_id), body, kind="followups", limit=limit, cursor=cursor
    )
