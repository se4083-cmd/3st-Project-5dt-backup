"""Database queries only; identity and domain decisions belong to services/policy."""

import base64
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, false, or_, select

from app.db import utcnow
from app.errors import APIError
from app.model_constraints import team_categories, user_team_scopes
from app.models import assignments, customers, messages, orders, teams, tickets, users


def row(session, table, *conditions):
    return session.execute(select(table).where(*conditions)).mappings().first()


def customer_for(session, user):
    if user["role"] != "CUSTOMER":
        raise APIError(403, "CUSTOMER_ROLE_REQUIRED", user["user_id"], "USER", user["user_id"])
    customer = row(
        session, customers, customers.c.user_id == user["user_id"], customers.c.deleted_at.is_(None)
    )
    if not customer:
        raise APIError(403, "CUSTOMER_PROFILE_UNAVAILABLE", user["user_id"], "USER", user["user_id"])
    return customer


def agent_assignment_exists(agent_id=None, *, as_of=None):
    """A current assignment that its active agent can actually use.

    Shared by agent ticket authorization and exception-queue suppression.
    Aliases keep the correlated predicate safe inside other staff queries.
    Queue visibility still requires its own explicit capability and route scope.
    """
    assignment, agent = assignments.alias(), users.alias()
    grant, team, category = user_team_scopes.alias(), teams.alias(), team_categories.alias()
    conditions = [
        assignment.c.ticket_id == tickets.c.ticket_id,
        assignment.c.cycle_no == tickets.c.cycle_no,
        assignment.c.team_id == tickets.c.team_id,
        assignment.c.ended_at.is_(None),
        assignment.c.assigned_at <= (as_of if as_of is not None else utcnow()),
        agent.c.active.is_(True),
        agent.c.role == "AGENT",
        agent.c.team_id == assignment.c.team_id,
        team.c.active.is_(True),
        tickets.c.status.in_(["ASSIGNED", "IN_PROGRESS", "FOLLOWUP_PENDING", "WAITING_CUSTOMER"]),
    ]
    if agent_id is not None:
        conditions.append(agent.c.user_id == agent_id)
    return exists(
        select(1)
        .select_from(
            assignment.join(agent, assignment.c.agent_id == agent.c.user_id)
            .join(grant, and_(grant.c.user_id == agent.c.user_id, grant.c.team_id == assignment.c.team_id))
            .join(team, team.c.team_id == assignment.c.team_id)
            .join(
                category,
                and_(category.c.team_id == assignment.c.team_id, category.c.category == tickets.c.category),
            )
        )
        .where(*conditions)
    ).correlate(tickets)


def ticket_scope(user):
    """Use the same SQL predicate for list and object authorization."""
    if user["role"] == "CUSTOMER":
        return exists(
            select(1).where(
                customers.c.customer_id == tickets.c.customer_id,
                customers.c.user_id == user["user_id"],
                customers.c.deleted_at.is_(None),
            )
        )
    if user["role"] == "AGENT":
        return agent_assignment_exists(user["user_id"])
    team_allowed = exists(
        select(1)
        .select_from(user_team_scopes.join(teams))
        .where(
            user_team_scopes.c.user_id == user["user_id"],
            user_team_scopes.c.team_id == tickets.c.team_id,
            teams.c.active.is_(True),
        )
    )
    if user["role"] == "ADMIN":
        return team_allowed
    return false()


def encode_cursor(timestamp, identifier):
    return (
        base64.urlsafe_b64encode(json.dumps([timestamp.isoformat(), identifier]).encode())
        .decode()
        .rstrip("=")
    )


def decode_cursor(cursor):
    try:
        if len(cursor) > 512:
            raise ValueError()
        value = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if not isinstance(value, list) or len(value) != 2 or not all(isinstance(v, str) for v in value):
            raise ValueError()
        timestamp = datetime.fromisoformat(value[0])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError()
        return timestamp, str(UUID(value[1]))
    except (ValueError, TypeError, IndexError, OverflowError):
        raise APIError(422, "INVALID_CURSOR") from None


def page_rows(session, table, predicate, time_column, id_column, limit, cursor, *, ascending=False):
    query = select(table).where(predicate)
    if cursor:
        timestamp, identifier = decode_cursor(cursor)
        comparison = (time_column > timestamp) if ascending else (time_column < timestamp)
        id_comparison = (id_column > identifier) if ascending else (id_column < identifier)
        query = query.where(or_(comparison, and_(time_column == timestamp, id_comparison)))
    order = (time_column.asc(), id_column.asc()) if ascending else (time_column.desc(), id_column.desc())
    found = list(session.execute(query.order_by(*order).limit(limit + 1)).mappings())
    items = found[:limit]
    next_cursor = (
        encode_cursor(items[-1][time_column.name], items[-1][id_column.name]) if len(found) > limit else None
    )
    return items, next_cursor


def public_messages(session, ticket_id, limit, cursor=None, ascending=True):
    return page_rows(
        session,
        messages,
        and_(messages.c.ticket_id == ticket_id, messages.c.visibility == "PUBLIC"),
        messages.c.created_at,
        messages.c.message_id,
        limit,
        cursor,
        ascending=ascending,
    )


def get_user(session, user_id):
    return row(session, users, users.c.user_id == user_id)


def get_order(session, customer_id, order_id):
    return row(session, orders, orders.c.customer_id == customer_id, orders.c.order_id == order_id)
