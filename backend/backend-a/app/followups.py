"""Followup service and shared ownership policy.

Writers: user (NO KEY UPDATE) -> ticket/product -> followup. No job locks.
Resolution writers hold the same ticket lock before checking ALL blocking actions.
"""

import hashlib
import json
from uuid import uuid4

from sqlalchemy import and_, exists, false, func, or_, select

from app import audit
from app import repository as repo
from app.db import utcnow
from app.errors import APIError, denied
from app.model_constraints import idempotency_keys, user_team_scopes
from app.models import followup_actions as actions
from app.models import products, teams, tickets, users

ACTIVE = {"OPEN", "IN_PROGRESS"}


def require_staff(user):
    if user["role"] not in {"AGENT", "ADMIN"}:
        raise APIError(403, "STAFF_ROLE_REQUIRED", user["user_id"], "USER", user["user_id"])


def team_scope(user, column):
    grants, active_team = user_team_scopes.alias(), teams.alias()
    return exists(
        select(1)
        .select_from(grants.join(active_team, grants.c.team_id == active_team.c.team_id))
        .where(
            grants.c.user_id == user["user_id"], grants.c.team_id == column, active_team.c.active.is_(True)
        )
        .correlate_except(grants, active_team)
    )


def scope(user):
    if user["role"] == "ADMIN":
        # Responsibility team is the queue anchor, including currently unassigned tickets.
        # This does not grant ticket or customer360 access outside ticket_scope.
        return team_scope(user, actions.c.owner_team_id)
    if user["role"] == "AGENT":
        return exists(
            select(1).where(
                tickets.c.ticket_id == actions.c.ticket_id,
                tickets.c.team_id == actions.c.owner_team_id,
                repo.ticket_scope(user),
            )
        )
    if user["role"] == "CUSTOMER":
        return and_(
            actions.c.public_note.is_not(None),
            func.length(func.trim(actions.c.public_note)) > 0,
            exists(select(1).where(tickets.c.ticket_id == actions.c.ticket_id, repo.ticket_scope(user))),
        )
    return false()


def owner_valid_predicate(team_id, owner_id, ticket_id, *, as_of=None):
    """Set-based equivalent of ownership policy; NULL owner is not an owned task.

    Correlate the outer action/owner explicitly while keeping local aliases in
    their own SELECTs. ADMIN product ownership and AGENT assignment differ.
    """
    owner, grant, team = users.alias(), user_team_scopes.alias(), teams.alias()
    assigned = repo.agent_assignment_exists(owner.c.user_id, as_of=as_of).correlate(owner)
    valid_ticket = exists(
        select(1).where(tickets.c.ticket_id == ticket_id, tickets.c.team_id == team_id, assigned)
    ).correlate_except(tickets)
    return exists(
        select(1)
        .select_from(
            owner.join(grant, grant.c.user_id == owner.c.user_id).join(
                team, team.c.team_id == grant.c.team_id
            )
        )
        .where(
            owner.c.user_id == owner_id,
            owner.c.active.is_(True),
            grant.c.team_id == team_id,
            team.c.active.is_(True),
            or_(owner.c.role == "ADMIN", and_(owner.c.role == "AGENT", valid_ticket)),
        )
    ).correlate_except(owner, grant, team)


def owner_valid(session, team_id, owner_id, ticket):
    if owner_id is None:
        return bool(
            session.scalar(select(exists().where(teams.c.team_id == team_id, teams.c.active.is_(True))))
        )
    return bool(
        session.scalar(
            select(owner_valid_predicate(team_id, owner_id, ticket["ticket_id"] if ticket else None))
        )
    )


def staff_view(session, action):
    ticket = (
        repo.row(session, tickets, tickets.c.ticket_id == action["ticket_id"])
        if action["ticket_id"]
        else None
    )
    attention = action["status"] in ACTIVE and (
        action["owner_user_id"] is None
        or not owner_valid(session, action["owner_team_id"], action["owner_user_id"], ticket)
        or (ticket is not None and action["responsibility_cycle_no"] != ticket["cycle_no"])
    )
    return {**action, "revision": action["version"], "needs_handover": bool(attention)}


def get(session, user, action_id, *, staff):
    if staff:
        require_staff(user)
    else:
        repo.customer_for(session, user)
    found = repo.row(session, actions, actions.c.action_id == action_id, scope(user))
    if not found:
        raise denied(user["user_id"], "FOLLOWUP", action_id)
    audit.record(session, user["user_id"], "FOLLOWUP_READ", "FOLLOWUP", action_id)
    return staff_view(session, found) if staff else found


def list_actions(session, user, limit, cursor, *, staff, ticket_id=None, product_id=None, status=None):
    if staff:
        require_staff(user)
    else:
        repo.customer_for(session, user)
    predicates = [scope(user)]
    if ticket_id:
        predicates.append(actions.c.ticket_id == ticket_id)
    if product_id:
        predicates.append(actions.c.product_id == product_id)
    if status:
        predicates.append(actions.c.status == status)
    rows, next_cursor = repo.page_rows(
        session, actions, and_(*predicates), actions.c.created_at, actions.c.action_id, limit, cursor
    )
    audit.record(session, user["user_id"], "FOLLOWUP_LIST", "FOLLOWUP", None)
    return {"items": [staff_view(session, r) for r in rows] if staff else rows, "next_cursor": next_cursor}


def lock_parent(session, ticket_id, product_id):
    table, key = (tickets, tickets.c.ticket_id) if ticket_id else (products, products.c.product_id)
    return (
        session.execute(select(table).where(key == (ticket_id or product_id)).with_for_update())
        .mappings()
        .first()
    )


def check_team(session, user, team_id):
    if not session.scalar(
        select(exists().where(teams.c.team_id == team_id, team_scope(user, teams.c.team_id)))
    ):
        raise denied(user["user_id"], "TEAM", team_id)


def validate_values(session, user, values, ticket):
    check_team(session, user, values["owner_team_id"])
    if not owner_valid(session, values["owner_team_id"], values["owner_user_id"], ticket):
        raise APIError(409, "FOLLOWUP_OWNER_INVALID")
    if user["role"] == "AGENT" and (
        ticket is None
        or values["owner_user_id"] != user["user_id"]
        or values["owner_team_id"] != ticket["team_id"]
    ):
        raise APIError(409, "FOLLOWUP_OWNER_INVALID")
    if values["blocks_resolution"] and (ticket is None or ticket["status"] in {"RESOLVED", "CANCELLED"}):
        raise APIError(409, "TICKET_ALREADY_FINISHED")
    if ticket is None and values["blocks_resolution"]:
        raise APIError(409, "PRODUCT_CANNOT_BLOCK_RESOLUTION")


def create(session, user, body, key):
    require_staff(user)
    session.execute(
        select(users.c.user_id).where(users.c.user_id == user["user_id"]).with_for_update(key_share=True)
    ).one()
    ticket_id, product_id = (
        str(body.ticket_id) if body.ticket_id else None,
        str(body.product_id) if body.product_id else None,
    )
    parent = lock_parent(session, ticket_id, product_id)
    if not parent:
        raise denied(user["user_id"], "TICKET" if ticket_id else "PRODUCT", ticket_id or product_id)
    if ticket_id:
        if not session.scalar(
            select(exists().where(tickets.c.ticket_id == ticket_id, repo.ticket_scope(user)))
        ):
            raise denied(user["user_id"], "TICKET", ticket_id)
    elif user["role"] != "ADMIN":
        raise APIError(403, "ADMIN_ROLE_REQUIRED", user["user_id"], "PRODUCT", product_id)
    check_team(session, user, str(body.owner_team_id))
    digest = hashlib.sha256(
        json.dumps(
            {"operation": "FOLLOWUP_CREATE", "body": body.model_dump(mode="json")},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    old = repo.row(
        session,
        idempotency_keys,
        idempotency_keys.c.user_id == user["user_id"],
        idempotency_keys.c.key == key,
    )
    if old:
        if old["operation"] != "FOLLOWUP_CREATE" or old["request_hash"] != digest:
            raise APIError(409, "IDEMPOTENCY_CONFLICT")
        return old["response_snapshot"], True
    now = utcnow()
    if body.due_at is not None and body.due_at <= now:
        raise APIError(422, "FOLLOWUP_DUE_IN_PAST")
    values = body.model_dump(mode="python")
    values.update(
        ticket_id=ticket_id,
        product_id=product_id,
        owner_team_id=str(body.owner_team_id),
        owner_user_id=str(body.owner_user_id) if body.owner_user_id else None,
    )
    validate_values(session, user, values, parent if ticket_id else None)
    if ticket_id and user["role"] == "AGENT" and values["owner_team_id"] != parent["team_id"]:
        raise APIError(409, "FOLLOWUP_OWNER_INVALID")
    action_id = str(uuid4())
    from app.followup_schemas import FollowupReceipt

    result = FollowupReceipt(action_id=action_id, revision=1, created_at=now).model_dump(mode="json")
    with session.begin_nested():
        session.execute(
            actions.insert().values(
                **values,
                action_id=action_id,
                status="OPEN",
                version=1,
                cycle_no=parent["cycle_no"] if ticket_id else None,
                responsibility_cycle_no=parent["cycle_no"] if ticket_id else None,
                origin_team_id=values["owner_team_id"],
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            idempotency_keys.insert().values(
                user_id=user["user_id"],
                key=key,
                operation="FOLLOWUP_CREATE",
                request_hash=digest,
                followup_id=action_id,
                response_snapshot=result,
                created_at=now,
            )
        )
        audit.record(
            session,
            user["user_id"],
            "FOLLOWUP_CREATED",
            "FOLLOWUP",
            action_id,
            ticket=ticket_id,
            cycle=parent["cycle_no"] if ticket_id else None,
        )
    return result, False


def mutate(session, user, action_id, body, *, state=False):
    require_staff(user)
    session.execute(
        select(users.c.user_id).where(users.c.user_id == user["user_id"]).with_for_update(key_share=True)
    ).one()
    hint = repo.row(session, actions, actions.c.action_id == action_id)
    if not hint:
        raise denied(user["user_id"], "FOLLOWUP", action_id)
    parent = lock_parent(session, hint["ticket_id"], hint["product_id"])
    found = (
        session.execute(select(actions).where(actions.c.action_id == action_id).with_for_update())
        .mappings()
        .one()
    )
    if not session.scalar(select(exists().where(actions.c.action_id == action_id, scope(user)))):
        raise denied(user["user_id"], "FOLLOWUP", action_id)
    if found["version"] != body.expected_revision:
        raise APIError(409, "FOLLOWUP_REVISION_CONFLICT")
    if found["status"] not in ACTIVE:
        raise APIError(409, "FOLLOWUP_TERMINAL")
    ticket = parent if found["ticket_id"] else None
    now = utcnow()
    if state:
        if body.status == found["status"] or body.status == "OPEN":
            raise APIError(409, "FOLLOWUP_TRANSITION_NOT_ALLOWED")
        if body.status != "CANCELLED":
            if (
                found["owner_user_id"] is None
                or not owner_valid(session, found["owner_team_id"], found["owner_user_id"], ticket)
                or (ticket is not None and found["responsibility_cycle_no"] != ticket["cycle_no"])
            ):
                raise APIError(409, "FOLLOWUP_TAKEOVER_REQUIRED")
        changes = {
            "status": body.status,
            "completed_at": now if body.status == "DONE" else None,
            "cancelled_at": now if body.status == "CANCELLED" else None,
            "cancellation_reason": body.cancellation_reason,
        }
    else:
        changes = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
        for field in ("owner_user_id", "owner_team_id"):
            if changes.get(field) is not None:
                changes[field] = str(changes[field])
        if "due_at" in changes and changes["due_at"] is not None and changes["due_at"] <= now:
            raise APIError(422, "FOLLOWUP_DUE_IN_PAST")
        owner_change = bool({"owner_user_id", "owner_team_id"} & changes.keys())
        if (
            user["role"] == "AGENT"
            and not owner_change
            and (
                found["owner_user_id"] != user["user_id"]
                or (ticket is not None and found["responsibility_cycle_no"] != ticket["cycle_no"])
            )
        ):
            raise APIError(409, "FOLLOWUP_TAKEOVER_REQUIRED")
        validate_values(session, user, {**found, **changes}, ticket)
        if owner_change and ticket is not None:
            changes["responsibility_cycle_no"] = ticket["cycle_no"]
    if user["role"] == "AGENT" and state and found["owner_user_id"] != user["user_id"]:
        raise APIError(409, "FOLLOWUP_TAKEOVER_REQUIRED")
    with session.begin_nested():
        session.execute(
            actions.update()
            .where(actions.c.action_id == action_id)
            .values(**changes, version=found["version"] + 1, updated_at=now)
        )
        audit.record(
            session,
            user["user_id"],
            "FOLLOWUP_STATE_CHANGED" if state else "FOLLOWUP_UPDATED",
            "FOLLOWUP",
            action_id,
            ticket=found["ticket_id"],
            cycle=found["cycle_no"],
            reason=(body.cancellation_reason or "AUTHORIZED") if state else "AUTHORIZED",
        )
    return staff_view(session, {**found, **changes, "version": found["version"] + 1, "updated_at": now})
