import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response

from app import audit, schemas, services, ticket_commands
from app.dependencies import DB, User
from app.errors import APIError

router = APIRouter(prefix="/api/v1")
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=512)]
IdempotencyKey = Annotated[str, Header(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]


@router.post("/auth/login", response_model=schemas.Token, tags=["auth"])
def login(body: schemas.Login, request: Request, session: DB):
    return services.login(session, body, request.app.state.settings)


@router.get("/auth/me", response_model=schemas.CurrentUser, tags=["auth"])
def me(session: DB, user: User):
    audit.record(session, user["user_id"], "READ_SELF", "USER", user["user_id"])
    return user


@router.get("/orders", response_model=schemas.Page[schemas.OrderPublic], tags=["orders"])
def orders(session: DB, user: User, limit: Limit = 20, cursor: Cursor = None):
    return services.order_list(session, user, limit, cursor)


@router.get("/orders/{order_id}", response_model=schemas.OrderPublic, tags=["orders"])
def order(order_id: UUID, session: DB, user: User):
    return services.order_detail(session, user, str(order_id))


@router.post(
    "/tickets",
    response_model=schemas.TicketReceipt,
    status_code=201,
    tags=["tickets"],
    responses={200: {"model": schemas.TicketReceipt, "description": "Idempotent replay"}},
)
def submit(
    body: schemas.TicketCreate,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=128)],
):
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", idempotency_key):
        raise APIError(422, "INVALID_IDEMPOTENCY_KEY")
    result, replay = services.submit_ticket(session, user, body, idempotency_key)
    if replay:
        response.status_code = 200
    response.headers["Idempotency-Replayed"] = str(replay).lower()
    response.headers["Location"] = f"/api/v1/tickets/{result['ticket_id']}"
    return result


@router.get("/tickets", response_model=schemas.Page[schemas.TicketPublic], tags=["tickets"])
def tickets(session: DB, user: User, limit: Limit = 20, cursor: Cursor = None):
    return services.ticket_list(session, user, limit, cursor)


@router.get("/tickets/{ticket_id}", response_model=schemas.TicketDetail, tags=["tickets"])
def ticket(ticket_id: UUID, session: DB, user: User):
    return services.ticket_detail(session, user, str(ticket_id))


@router.get(
    "/tickets/{ticket_id}/messages", response_model=schemas.Page[schemas.MessagePublic], tags=["tickets"]
)
def messages(ticket_id: UUID, session: DB, user: User, limit: Limit = 20, cursor: Cursor = None):
    return services.message_list(session, user, str(ticket_id), limit, cursor)


def action_result(response, ticket_id, result):
    receipt, replay = result
    response.status_code = 200 if replay else 201
    response.headers["Idempotency-Replayed"] = str(replay).lower()
    response.headers["Location"] = f"/api/v1/tickets/{ticket_id}"
    return receipt


@router.post(
    "/tickets/{ticket_id}/reopen",
    response_model=schemas.TicketActionReceipt,
    status_code=201,
    tags=["tickets"],
    responses={200: {"model": schemas.TicketActionReceipt, "description": "Idempotent replay"}},
)
def reopen(
    ticket_id: UUID,
    body: schemas.ReopenRequest,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: IdempotencyKey,
):
    return action_result(
        response,
        ticket_id,
        ticket_commands.change_cycle(
            session, user, str(ticket_id), body, idempotency_key, operation="REOPEN"
        ),
    )


@router.post(
    "/tickets/{ticket_id}/request-agent",
    response_model=schemas.TicketActionReceipt,
    status_code=201,
    tags=["tickets"],
    responses={200: {"model": schemas.TicketActionReceipt, "description": "Idempotent replay"}},
)
def request_agent(
    ticket_id: UUID,
    body: schemas.AgentRequest,
    session: DB,
    user: User,
    response: Response,
    idempotency_key: IdempotencyKey,
):
    return action_result(
        response,
        ticket_id,
        ticket_commands.change_cycle(
            session, user, str(ticket_id), body, idempotency_key, operation="REQUEST_AGENT"
        ),
    )
