"""Snapshot workload facts only. No scheduling, assignment, or deadline writes."""

import base64
import hashlib
import json
from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select

from app import audit, repository
from app.automation_control import capability
from app.errors import APIError
from app.followups import owner_valid_predicate
from app.model_constraints import user_team_scopes
from app.models import assignments, followup_actions, teams, tickets, users
from app.staff_models import queue_routes
from app.workload_schemas import (
    AgentWorkload,
    DeadlineCounts,
    TicketCounts,
    UnassignedCounts,
    WorkloadPage,
    WorkloadTeamQueue,
    WorkloadTotals,
)

CATEGORIES = ("ACCOUNT", "DELIVERY", "PAYMENT", "PRODUCT", "REFUND", "RETURN", "FAQ", "UNCLASSIFIED")


def deadline_state(column, as_of):
    return case(
        (column.is_(None), "no_due_date"),
        (column < as_of, "overdue"),
        (column <= as_of + timedelta(hours=2), "due_soon"),
        else_="on_time",
    )


def category_value(column):
    # Unknown DB text is counted once without echoing arbitrary business text.
    return case((column.in_(CATEGORIES), column), else_="UNCLASSIFIED")


def handling_path():
    """Declared current ticket path, never evidence of an AI/worker executing.

    Only HANDOFF_PENDING + HUMAN explicitly means waiting for human assignment.
    Failed/retrying jobs and global pause do not change the declared path.
    Missing/contradictory ticket states remain unknown, without history guesses.
    """
    return case(
        (
            and_(
                tickets.c.requested_mode == "AUTO",
                tickets.c.resolution_mode.is_(None),
                tickets.c.status.in_(["OPEN", "PROCESSING", "WAITING_CUSTOMER"]),
            ),
            "automatic_path",
        ),
        (
            and_(
                tickets.c.requested_mode == "HUMAN",
                tickets.c.resolution_mode.is_(None),
                tickets.c.status == "HANDOFF_PENDING",
            ),
            "human_assignment_waiting",
        ),
        else_="unknown",
    )


def add_deadline(result, state, count):
    result.total += count
    setattr(result, state, getattr(result, state) + count)


def add_ticket(result, row):
    add_deadline(result, row["deadline"], row["n"])
    result.waiting_customer += row["waiting"]
    result.by_category[row["category"]] = result.by_category.get(row["category"], 0) + row["n"]


def selected_teams(session, user, team_id):
    allowed = set(
        session.scalars(
            select(user_team_scopes.c.team_id)
            .join(teams)
            .where(user_team_scopes.c.user_id == user["user_id"], teams.c.active.is_(True))
        )
    )
    if user["role"] == "AGENT":
        allowed &= {user["team_id"]}
    if team_id is not None:
        if team_id not in allowed:
            raise APIError(403, "WORKLOAD_TEAM_SCOPE_DENIED", user["user_id"])
        allowed = {team_id}
    return sorted(allowed)


def decode_cursor(cursor, fingerprint):
    try:
        if len(cursor) > 512:
            raise ValueError()
        value = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(item, str) for item in value)
            or value[0] != fingerprint
        ):
            raise ValueError()
        return str(UUID(value[1]))
    except (ValueError, TypeError, IndexError):
        raise APIError(422, "INVALID_CURSOR") from None


def unassigned_counts(session, as_of, team_ids, *, unrouted=False):
    route = queue_routes
    active_route = exists(select(1).where(teams.c.team_id == route.c.team_id, teams.c.active.is_(True)))
    route_scope = (
        or_(route.c.team_id.is_(None), ~active_route)
        if unrouted
        else and_(route.c.team_id.in_(team_ids), active_route)
    )
    category = category_value(tickets.c.category)
    deadline = deadline_state(tickets.c.sla_due_at, as_of)
    path = handling_path()
    remaining_assignment = exists(
        select(1).where(assignments.c.ticket_id == tickets.c.ticket_id, assignments.c.ended_at.is_(None))
    )
    rows = session.execute(
        select(
            category.label("category"),
            deadline.label("deadline"),
            path.label("handling_path"),
            func.count().label("n"),
            func.sum(case((tickets.c.status == "WAITING_CUSTOMER", 1), else_=0)).label("waiting"),
            func.sum(case((remaining_assignment, 1), else_=0)).label("invalid"),
        )
        .select_from(
            tickets.outerjoin(
                route, and_(route.c.ticket_id == tickets.c.ticket_id, route.c.cycle_no == tickets.c.cycle_no)
            )
        )
        .where(
            tickets.c.status.not_in(["RESOLVED", "CANCELLED"]),
            ~repository.agent_assignment_exists(as_of=as_of),
            route_scope,
        )
        .group_by(category, deadline, path)
    ).mappings()
    result = UnassignedCounts()
    for row in rows:
        add_ticket(result, row)
        result.invalid_assignment_count += row["invalid"]
        field = row["handling_path"]
        setattr(result.by_handling_path, field, getattr(result.by_handling_path, field) + row["n"])
    return result


def ticket_facts(roster, as_of):
    # EXISTS preserves one fact per ticket/cycle despite historical assignment rows.
    return (
        select(
            roster.c.agent_id,
            tickets.c.ticket_id,
            tickets.c.cycle_no,
            tickets.c.category,
            tickets.c.status,
            tickets.c.sla_due_at,
        )
        .select_from(tickets.join(roster, tickets.c.team_id == roster.c.team_id))
        .where(repository.agent_assignment_exists(roster.c.agent_id, as_of=as_of).correlate(roster))
        .distinct()
        .cte("workload_ticket_facts")
    )


def ticket_counts(session, roster, page_ids, as_of):
    facts = ticket_facts(roster, as_of)
    # Non-page agents collapse into a NULL bucket: bounded aggregate result size,
    # while scope totals cover the complete roster, independently of pagination.
    bucket = case((facts.c.agent_id.in_(page_ids), facts.c.agent_id), else_=None)
    category, deadline = category_value(facts.c.category), deadline_state(facts.c.sla_due_at, as_of)
    rows = session.execute(
        select(
            bucket.label("agent_id"),
            category.label("category"),
            deadline.label("deadline"),
            func.count().label("n"),
            func.sum(case((facts.c.status == "WAITING_CUSTOMER", 1), else_=0)).label("waiting"),
        ).group_by(bucket, category, deadline)
    ).mappings()
    total, personal = TicketCounts(), {key: TicketCounts() for key in page_ids}
    for row in rows:
        add_ticket(total, row)
        if row["agent_id"] is not None:
            add_ticket(personal[row["agent_id"]], row)
    return total, personal


def followup_counts(session, team_ids, page_ids, as_of, *, self_id=None):
    action = followup_actions
    current_responsibility = or_(
        action.c.ticket_id.is_(None),
        exists(
            select(1).where(
                tickets.c.ticket_id == action.c.ticket_id,
                tickets.c.cycle_no == action.c.responsibility_cycle_no,
            )
        ),
    )
    valid = and_(
        current_responsibility,
        owner_valid_predicate(
            action.c.owner_team_id, action.c.owner_user_id, action.c.ticket_id, as_of=as_of
        ),
    )
    kind = case((~valid, "WAITING"), (users.c.role == "ADMIN", "ADMIN"), else_="AGENT")
    bucket = case(
        (and_(valid, users.c.role == "AGENT", users.c.user_id.in_(page_ids)), users.c.user_id), else_=None
    )
    deadline = deadline_state(action.c.due_at, as_of)
    query = (
        select(
            bucket.label("agent_id"), kind.label("kind"), deadline.label("deadline"), func.count().label("n")
        )
        .select_from(action.outerjoin(users, action.c.owner_user_id == users.c.user_id))
        .where(action.c.owner_team_id.in_(team_ids), action.c.status.in_(["OPEN", "IN_PROGRESS"]))
    )
    if self_id is not None:
        query = query.where(action.c.owner_user_id == self_id, valid)
    rows = session.execute(query.group_by(bucket, kind, deadline)).mappings()
    totals = {kind: DeadlineCounts() for kind in ("AGENT", "ADMIN", "WAITING")}
    personal = {key: DeadlineCounts() for key in page_ids}
    for row in rows:
        add_deadline(totals[row["kind"]], row["deadline"], row["n"])
        if row["agent_id"] is not None:
            add_deadline(personal[row["agent_id"]], row["deadline"], row["n"])
    return totals, personal


def view(session, user, *, team_id=None, agent_id=None, include_unrouted=False, limit=20, cursor=None):
    if user["role"] not in {"AGENT", "ADMIN"}:
        raise APIError(403, "STAFF_ROLE_REQUIRED", user["user_id"])
    is_self = user["role"] == "AGENT"
    if is_self:
        if agent_id is not None and agent_id != user["user_id"]:
            raise APIError(403, "WORKLOAD_SELF_ONLY", user["user_id"])
    else:
        capability(session, user, "WORKLOAD_READ", admin=True)
    if include_unrouted:
        capability(session, user, "UNROUTED_QUEUE_READ", admin=True)
    team_ids = selected_teams(session, user, team_id)
    roster_query = select(users.c.user_id.label("agent_id"), users.c.team_id).where(
        users.c.role == "AGENT",
        users.c.active.is_(True),
        users.c.team_id.in_(team_ids),
        exists(
            select(1).where(
                user_team_scopes.c.user_id == users.c.user_id,
                user_team_scopes.c.team_id == users.c.team_id,
            )
        ),
    )
    if is_self:
        roster_query = roster_query.where(users.c.user_id == user["user_id"])
    roster = roster_query.cte("workload_roster")
    page_query = select(roster)
    if agent_id is not None:
        # Generic missing/out-of-scope result, without looking up another team.
        if not is_self and not session.scalar(select(exists().where(roster.c.agent_id == agent_id))):
            raise APIError(404, "WORKLOAD_AGENT_NOT_FOUND", user["user_id"])
        page_query = page_query.where(roster.c.agent_id == agent_id)
    matching = session.scalar(select(func.count()).select_from(page_query.subquery()))
    total_agents = session.scalar(select(func.count()).select_from(roster))
    fingerprint = hashlib.sha256(
        json.dumps([user["user_id"], user["role"], team_ids, agent_id, include_unrouted]).encode()
    ).hexdigest()
    if cursor:
        page_query = page_query.where(roster.c.agent_id > decode_cursor(cursor, fingerprint))
    page = list(session.execute(page_query.order_by(roster.c.agent_id).limit(limit + 1)).mappings())
    page_ids = [row["agent_id"] for row in page[:limit]]
    as_of = session.info["snapshot_as_of"]
    all_tickets, agent_tickets = ticket_counts(session, roster, page_ids, as_of)
    all_followups, agent_followups = followup_counts(
        session, team_ids, page_ids, as_of, self_id=user["user_id"] if is_self else None
    )
    items = [
        AgentWorkload(
            agent_id=row["agent_id"],
            team_id=row["team_id"],
            tickets=agent_tickets[row["agent_id"]],
            followups=agent_followups[row["agent_id"]],
        )
        for row in page[:limit]
    ]
    page_totals = WorkloadTotals()
    for item in items:
        for state in ("overdue", "due_soon", "on_time", "no_due_date"):
            add_deadline(page_totals.tickets, state, getattr(item.tickets, state))
            add_deadline(page_totals.followups, state, getattr(item.followups, state))
        page_totals.tickets.waiting_customer += item.tickets.waiting_customer
        for category, count in item.tickets.by_category.items():
            page_totals.tickets.by_category[category] = (
                page_totals.tickets.by_category.get(category, 0) + count
            )
    next_cursor = None
    if len(page) > limit:
        next_cursor = (
            base64.urlsafe_b64encode(json.dumps([fingerprint, page_ids[-1]]).encode()).decode().rstrip("=")
        )
    result = WorkloadPage(
        as_of=as_of,
        view="SELF" if is_self else "TEAM",
        team_ids=team_ids,
        agent_filter=agent_id,
        total_agents=total_agents,
        matching_agents=matching,
        items=items,
        next_cursor=next_cursor,
        scope_totals=WorkloadTotals(tickets=all_tickets, followups=all_followups["AGENT"]),
        page_totals=page_totals,
        team_queue=None
        if is_self
        else WorkloadTeamQueue(
            unassigned=unassigned_counts(session, as_of, team_ids),
            waiting_followups=all_followups["WAITING"],
            admin_owned_followups=all_followups["ADMIN"],
        ),
        unrouted=unassigned_counts(session, as_of, [], unrouted=True) if include_unrouted else None,
    )
    audit.record(session, user["user_id"], "READ_WORKLOAD", "WORKLOAD", None, reason=result.view)
    return result
