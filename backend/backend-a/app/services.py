import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import audit, auth
from app import repository as repo
from app.db import utcnow
from app.errors import APIError, denied
from app.model_constraints import idempotency_keys
from app.models import automation_jobs, messages, orders, tickets, users

STAGES = {
    "OPEN": "RECEIVED",
    "PROCESSING": "PROCESSING",
    "WAITING_CUSTOMER": "NEEDS_INFORMATION",
    "HANDOFF_PENDING": "WAITING_FOR_SUPPORT",
    "ASSIGNED": "IN_SUPPORT",
    "IN_PROGRESS": "IN_SUPPORT",
    "FOLLOWUP_PENDING": "FOLLOWUP",
    "RESOLVED": "COMPLETED",
    "CANCELLED": "CANCELLED",
}


def public_ticket(ticket):
    human = (
        ticket["resolution_mode"] == "HUMAN"
        or ticket["requested_mode"] == "HUMAN"
        or ticket["status"] in ("HANDOFF_PENDING", "ASSIGNED", "IN_PROGRESS", "FOLLOWUP_PENDING")
    )
    return {
        **{k: ticket[k] for k in ("ticket_id", "order_id", "product_id", "created_at", "updated_at")},
        "stage": STAGES[ticket["status"]],
        "handling_mode": "HUMAN" if human else "AUTOMATED",
        "revision": ticket["version"],
        "cycle_no": ticket["cycle_no"],
    }


def public_message(message):
    return {
        **{k: message[k] for k in ("message_id", "cycle_no", "body", "created_at")},
        "sender": "CUSTOMER" if message["role"] == "CUSTOMER" else "SUPPORT",
    }


def login(session, body, settings):
    user = repo.row(session, users, users.c.login_name == body.login_name.strip().lower())
    valid = auth.verify_password(body.password, user["password_hash"] if user else "")
    if (
        not user
        or not valid
        or not user["active"]
        or (settings.app_env == "production" and user["is_dev_account"])
    ):
        raise APIError(401, "INVALID_CREDENTIALS", user["user_id"] if user else None, "AUTH")
    audit.record(session, user["user_id"], "LOGIN", "USER", user["user_id"])
    return {
        "access_token": auth.issue_token(user["user_id"], settings),
        "expires_in": settings.token_minutes * 60,
    }


def authorized_ticket(session, user, ticket_id):
    found = repo.row(session, tickets, tickets.c.ticket_id == ticket_id, repo.ticket_scope(user))
    if not found:
        raise denied(user["user_id"], "TICKET", ticket_id)
    return found


def order_detail(session, user, order_id):
    customer = repo.customer_for(session, user)
    found = repo.get_order(session, customer["customer_id"], order_id)
    if not found:
        raise denied(user["user_id"], "ORDER", order_id)
    audit.record(session, user["user_id"], "READ", "ORDER", order_id)
    return found


def order_list(session, user, limit, cursor):
    customer = repo.customer_for(session, user)
    rows, next_cursor = repo.page_rows(
        session,
        orders,
        orders.c.customer_id == customer["customer_id"],
        orders.c.placed_at,
        orders.c.order_id,
        limit,
        cursor,
    )
    audit.record(session, user["user_id"], "LIST", "ORDER", None)
    return {"items": rows, "next_cursor": next_cursor}


def ticket_list(session, user, limit, cursor):
    rows, next_cursor = repo.page_rows(
        session, tickets, repo.ticket_scope(user), tickets.c.created_at, tickets.c.ticket_id, limit, cursor
    )
    audit.record(session, user["user_id"], "LIST", "TICKET", None)
    return {"items": [public_ticket(t) for t in rows], "next_cursor": next_cursor}


def ticket_detail(session, user, ticket_id):
    ticket = authorized_ticket(session, user, ticket_id)
    # Bounded most recent 50 messages, presented chronologically.
    rows, more = repo.public_messages(session, ticket_id, 50, ascending=False)
    audit.record(session, user["user_id"], "READ", "TICKET", ticket_id, ticket=ticket_id)
    return {
        **public_ticket(ticket),
        "messages": [public_message(m) for m in reversed(rows)],
        "messages_has_more": more is not None,
    }


def message_list(session, user, ticket_id, limit, cursor):
    authorized_ticket(session, user, ticket_id)
    rows, next_cursor = repo.public_messages(session, ticket_id, limit, cursor)
    audit.record(session, user["user_id"], "LIST_MESSAGES", "TICKET", ticket_id, ticket=ticket_id)
    return {"items": [public_message(m) for m in rows], "next_cursor": next_cursor}


def _existing_receipt(session, user_id, key, request_hash):
    existing = repo.row(
        session, idempotency_keys, idempotency_keys.c.user_id == user_id, idempotency_keys.c.key == key
    )
    if not existing:
        return None
    if existing["operation"] != "CREATE_TICKET" or existing["request_hash"] != request_hash:
        raise APIError(409, "IDEMPOTENCY_CONFLICT")
    return {"ticket_id": existing["ticket_id"], "created_at": existing["created_at"]}


def submit_ticket(session, user, body, key):
    customer = repo.customer_for(session, user)
    # Global user/key namespace also covers reopen and agent requests.
    session.execute(select(users.c.user_id).where(users.c.user_id == user["user_id"]).with_for_update()).one()
    canonical = json.dumps(
        body.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    request_hash = hashlib.sha256(canonical.encode()).hexdigest()
    receipt = _existing_receipt(session, user["user_id"], key, request_hash)
    if receipt:
        return receipt, True
    product_id = None
    if body.order_id:
        order = repo.get_order(session, customer["customer_id"], str(body.order_id))
        if not order:
            raise denied(user["user_id"], "ORDER", str(body.order_id))
        if order["product_id"] is None:
            raise APIError(409, "ORDER_PRODUCT_UNAVAILABLE")
        product_id = order["product_id"]
    now = utcnow()
    ticket_id = str(uuid4())
    try:
        # Savepoint lets a concurrent unique-key loser discard all its writes,
        # then read the winner under PostgreSQL READ COMMITTED.
        with session.begin_nested():
            session.execute(
                tickets.insert().values(
                    ticket_id=ticket_id,
                    customer_id=customer["customer_id"],
                    order_id=str(body.order_id) if body.order_id else None,
                    product_id=product_id,
                    sla_due_at=now + timedelta(hours=24),
                    created_at=now,
                    updated_at=now,
                )
            )
            session.execute(
                idempotency_keys.insert().values(
                    user_id=user["user_id"],
                    key=key,
                    request_hash=request_hash,
                    ticket_id=ticket_id,
                    created_at=now,
                )
            )
            session.execute(
                messages.insert().values(
                    message_id=str(uuid4()),
                    ticket_id=ticket_id,
                    cycle_no=1,
                    role="CUSTOMER",
                    direction="IN",
                    body=body.message,
                    visibility="PUBLIC",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.execute(
                automation_jobs.insert().values(
                    job_id=str(uuid4()),
                    ticket_id=ticket_id,
                    cycle_no=1,
                    expected_ticket_version=1,
                    created_at=now,
                    updated_at=now,
                    next_attempt_at=now,
                )
            )
            audit.record(
                session,
                user["user_id"],
                "TICKET_CREATED",
                "TICKET",
                ticket_id,
                reason="CUSTOMER_SUBMITTED",
                ticket=ticket_id,
            )
    except IntegrityError:
        receipt = _existing_receipt(session, user["user_id"], key, request_hash)
        if receipt:
            return receipt, True
        raise
    return {"ticket_id": ticket_id, "created_at": now}, False
