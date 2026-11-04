"""Snapshot hints only. No assignment, job, route, deadline or reservation writes."""

import base64
import hashlib
import json
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select

from app import audit, workload
from app import repository as repo
from app.automation_control import capability
from app.errors import APIError, denied
from app.model_constraints import team_categories
from app.models import assignments, automation_jobs, teams, tickets, users
from app.recommendation_schemas import RecommendationCandidate, RecommendationItem, RecommendationPage
from app.staff_models import queue_routes, staff_permissions

RULE_VERSION = "WORKLOAD_PRIORITY_V1"
CANDIDATE_REASONS = [
    "ACTIVE_AGENT",
    "ROUTE_TEAM_MATCH",
    "CATEGORY_SUPPORTED",
    "NORMALIZED_SCOPE_PRESENT",
    "ORDERED_BY_ACTIVE_TICKET_COUNT",
    "ORDERED_BY_OVERDUE_COUNT",
    "STABLE_USER_ID_TIEBREAK",
]


def cursor_value(cursor, fingerprint):
    try:
        if not isinstance(cursor, str) or len(cursor) > 512:
            raise ValueError()
        value = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if (
            not isinstance(value, list)
            or len(value) != 3
            or value[0] != fingerprint
            or not isinstance(value[2], str)
        ):
            raise ValueError()
        due = datetime.fromisoformat(value[1]) if isinstance(value[1], str) else None
        if value[1] is not None and (not due or due.tzinfo is None or due.utcoffset() is None):
            raise ValueError()
        return due, str(UUID(value[2]))
    except (ValueError, TypeError, IndexError, OverflowError):
        raise APIError(422, "INVALID_CURSOR") from None


def targets(as_of):
    route = queue_routes
    joined = tickets.outerjoin(
        route, and_(route.c.ticket_id == tickets.c.ticket_id, route.c.cycle_no == tickets.c.cycle_no)
    )
    active_route = exists(select(1).where(teams.c.team_id == route.c.team_id, teams.c.active.is_(True)))
    valid = repo.agent_assignment_exists(as_of=as_of)
    physical = exists(
        select(1).where(assignments.c.ticket_id == tickets.c.ticket_id, assignments.c.ended_at.is_(None))
    )
    failed = exists(
        select(1).where(
            automation_jobs.c.ticket_id == tickets.c.ticket_id,
            automation_jobs.c.cycle_no == tickets.c.cycle_no,
            automation_jobs.c.job_kind == "AUTO",
            automation_jobs.c.status == "FAILED",
        )
    )
    ready = and_(
        tickets.c.requested_mode == "HUMAN",
        tickets.c.status == "HANDOFF_PENDING",
        tickets.c.resolution_mode.is_(None),
        ~valid,
    )
    query = select(
        tickets.c.ticket_id,
        tickets.c.cycle_no,
        tickets.c.version,
        tickets.c.category,
        tickets.c.requested_mode,
        tickets.c.status,
        tickets.c.resolution_mode,
        tickets.c.sla_due_at,
        route.c.team_id.label("route_team_id"),
        route.c.revision.label("route_revision"),
        route.c.recorded_at.label("route_recorded_at"),
        active_route.label("active_route"),
        valid.label("valid_assignment"),
        physical.label("physical_assignment"),
        failed.label("failed_auto"),
        workload.deadline_state(tickets.c.sla_due_at, as_of).label("deadline"),
    ).select_from(joined)
    return query, ready, active_route


def rank_candidates(session, page, team_ids, limit, as_of):
    # All workload facts and candidate rankings are set-based, not one query per ticket/agent.
    roster = (
        select(users.c.user_id.label("agent_id"), users.c.team_id)
        .where(users.c.team_id.in_(team_ids), repo.agent_eligibility(users, users.c.team_id))
        .cte("recommendation_roster")
    )
    facts = workload.ticket_facts(roster, as_of)
    loads = (
        select(
            facts.c.agent_id,
            func.count().label("active_count"),
            func.sum(case((facts.c.sla_due_at < as_of, 1), else_=0)).label("overdue_count"),
        )
        .group_by(facts.c.agent_id)
        .cte("recommendation_loads")
    )
    ids = [
        p["ticket_id"]
        for p in page
        if p["eligible"]
        and p["active_route"]
        and p["category"] in workload.CATEGORIES
        and p["category"] != "UNCLASSIFIED"
    ]
    if not ids:
        return {}, {}
    query, _, _ = targets(as_of)
    page_tasks = query.where(tickets.c.ticket_id.in_(ids)).cte("recommendation_page_tasks")
    active = func.coalesce(loads.c.active_count, 0)
    overdue = func.coalesce(loads.c.overdue_count, 0)
    ranked = (
        select(
            page_tasks.c.ticket_id,
            users.c.user_id.label("agent_id"),
            users.c.team_id,
            func.row_number()
            .over(partition_by=page_tasks.c.ticket_id, order_by=(active, overdue, users.c.user_id))
            .label("rank"),
            func.count().over(partition_by=page_tasks.c.ticket_id).label("eligible_count"),
        )
        .select_from(
            page_tasks.join(
                users, repo.agent_eligibility(users, page_tasks.c.route_team_id, page_tasks.c.category)
            ).outerjoin(loads, loads.c.agent_id == users.c.user_id)
        )
        .cte("ranked_recommendation_candidates")
    )
    rows = list(
        session.execute(
            select(ranked).where(ranked.c.rank <= limit).order_by(ranked.c.ticket_id, ranked.c.rank)
        ).mappings()
    )
    agent_ids = sorted({r["agent_id"] for r in rows})
    if not agent_ids:
        return {}, {}
    _, ticket_counts = workload.ticket_counts(session, roster, agent_ids, as_of)
    _, followup_counts = workload.followup_counts(session, team_ids, agent_ids, as_of)
    by_ticket = {}
    for row in rows:
        by_ticket.setdefault(row["ticket_id"], []).append(
            RecommendationCandidate(
                agent_id=row["agent_id"],
                team_id=row["team_id"],
                tickets=ticket_counts[row["agent_id"]],
                followups=followup_counts[row["agent_id"]],
                rank=row["rank"],
                reason_codes=CANDIDATE_REASONS,
            )
        )
    eligible_counts = {r["ticket_id"]: r["eligible_count"] for r in rows}
    return by_ticket, eligible_counts


def view(session, user, *, team_id=None, ticket_id=None, limit=20, candidate_limit=3, cursor=None):
    """Caller authenticates user identity and opens the repeatable-read snapshot.
    snapshot_as_of must be set before authentication; caller commits minimal audit.
    """
    if "snapshot_as_of" not in session.info:
        raise ValueError("AUTHENTICATED_SNAPSHOT_REQUIRED")
    if (
        session.get_bind().dialect.name == "postgresql"
        and session.connection().get_isolation_level() != "REPEATABLE READ"
    ):
        raise APIError(503, "RECOMMENDATION_SNAPSHOT_REQUIRED")
    current = repo.get_user(session, user["user_id"])
    if not current or not current["active"]:
        raise APIError(401, "INVALID_CREDENTIALS")
    user = current
    capability(session, user, "ASSIGNMENT_RECOMMEND", admin=True)
    if not 1 <= limit <= 50 or not 1 <= candidate_limit <= 10 or (ticket_id and cursor):
        raise APIError(422, "RECOMMENDATION_FILTER_INVALID")
    try:
        team_ids = workload.selected_teams(session, user, team_id)
    except APIError:
        raise APIError(403, "RECOMMENDATION_TEAM_SCOPE_DENIED", user["user_id"]) from None
    as_of = session.info["snapshot_as_of"]
    query, ready, active_route = targets(as_of)
    scoped = and_(active_route, queue_routes.c.team_id.in_(team_ids))
    fingerprint = hashlib.sha256(
        json.dumps([RULE_VERSION, user["user_id"], team_ids, ticket_id, candidate_limit]).encode()
    ).hexdigest()
    next_cursor = None
    if ticket_id:
        visible = scoped
        if team_id is None and session.scalar(
            select(
                exists().where(
                    staff_permissions.c.user_id == user["user_id"],
                    staff_permissions.c.permission == "UNROUTED_QUEUE_READ",
                )
            )
        ):
            visible = or_(visible, ~active_route)
        row = (
            session.execute(
                query.add_columns(ready.label("eligible")).where(tickets.c.ticket_id == ticket_id, visible)
            )
            .mappings()
            .first()
        )
        if not row:
            raise denied(user["user_id"], "ASSIGNMENT_RECOMMENDATION", ticket_id)
        page = [row]
        total = 1
    else:
        filtered = query.add_columns(ready.label("eligible")).where(scoped, ready)
        total = session.scalar(select(func.count()).select_from(filtered.subquery()))
        if cursor:
            due, identifier = cursor_value(cursor, fingerprint)
            filtered = filtered.where(
                and_(tickets.c.sla_due_at.is_(None), tickets.c.ticket_id > identifier)
                if due is None
                else or_(
                    tickets.c.sla_due_at > due,
                    tickets.c.sla_due_at.is_(None),
                    and_(tickets.c.sla_due_at == due, tickets.c.ticket_id > identifier),
                )
            )
        priority = case(
            (tickets.c.sla_due_at < as_of, 0),
            (tickets.c.sla_due_at <= as_of + timedelta(hours=2), 1),
            else_=2,
        )
        rows = list(
            session.execute(
                filtered.order_by(
                    priority, tickets.c.sla_due_at.asc().nulls_last(), tickets.c.ticket_id
                ).limit(limit + 1)
            ).mappings()
        )
        page = rows[:limit]
        if len(rows) > limit:
            last = page[-1]
            next_cursor = (
                base64.urlsafe_b64encode(
                    json.dumps(
                        [
                            fingerprint,
                            last["sla_due_at"].isoformat() if last["sla_due_at"] else None,
                            last["ticket_id"],
                        ]
                    ).encode()
                )
                .decode()
                .rstrip("=")
            )
    candidates, eligible_counts = rank_candidates(session, page, team_ids, candidate_limit, as_of)
    supported = (
        {
            (r.team_id, r.category)
            for r in session.execute(select(team_categories).where(team_categories.c.team_id.in_(team_ids)))
        }
        if page
        else set()
    )
    items = []
    for row in page:
        reasons = ["WAITING_START_UNRECORDED"]
        state = "AVAILABLE"
        if not row["active_route"]:
            reasons.append("UNROUTED_NO_RECOMMENDATION")
            state = "UNAVAILABLE"
        elif row["valid_assignment"]:
            reasons.append("ALREADY_VALIDLY_ASSIGNED")
            state = "UNAVAILABLE"
        elif row["requested_mode"] != "HUMAN":
            reasons.append("NOT_HUMAN_PATH")
            state = "UNAVAILABLE"
        elif not row["eligible"]:
            reasons.append("STATE_NOT_ASSIGNABLE")
            state = "UNAVAILABLE"
        else:
            reasons.extend(
                [
                    "HUMAN_HANDOFF_PENDING",
                    {
                        "overdue": "DEADLINE_OVERDUE",
                        "due_soon": "DEADLINE_DUE_SOON",
                        "on_time": "DEADLINE_ON_TIME",
                        "no_due_date": "NO_DUE_DATE",
                    }[row["deadline"]],
                ]
            )
            if row["category"] not in workload.CATEGORIES or row["category"] == "UNCLASSIFIED":
                reasons.append("CATEGORY_UNKNOWN")
                state = "UNAVAILABLE"
            elif (row["route_team_id"], row["category"]) not in supported:
                reasons.append("ROUTE_CATEGORY_UNSUPPORTED")
                state = "UNAVAILABLE"
            elif not candidates.get(row["ticket_id"]):
                reasons.append("NO_ELIGIBLE_AGENT")
                state = "UNAVAILABLE"
        if row["failed_auto"]:
            reasons.append("FAILED_AUTO_HISTORY_PRESERVED")
        invalid = bool(row["physical_assignment"] and not row["valid_assignment"])
        if invalid:
            reasons.append("PHYSICAL_ASSIGNMENT_RECONCILIATION_REQUIRED")
            if state == "AVAILABLE":
                state = "CONDITIONAL"
        people = candidates.get(row["ticket_id"], []) if state != "UNAVAILABLE" else []
        n = eligible_counts.get(row["ticket_id"], 0) if state != "UNAVAILABLE" else 0
        items.append(
            RecommendationItem(
                ticket_id=row["ticket_id"],
                cycle_no=row["cycle_no"],
                ticket_revision=row["version"],
                route_revision=row["route_revision"],
                route_team_id=row["route_team_id"] if row["active_route"] else None,
                route_recorded_at=row["route_recorded_at"],
                category=row["category"] if row["category"] in workload.CATEGORIES else None,
                deadline_state=row["deadline"],
                due_at=row["sla_due_at"],
                recommendation_state=state,
                reason_codes=reasons,
                invalid_active_assignment_present=invalid,
                eligible_candidate_count=n,
                candidates_truncated=n > candidate_limit,
                candidates=people,
            )
        )
    result = RecommendationPage(
        as_of=as_of,
        expires_at=as_of + timedelta(seconds=30),
        team_ids=team_ids,
        ticket_filter=ticket_id,
        total=total,
        items=items,
        next_cursor=next_cursor,
    )
    audit.record(
        session, user["user_id"], "READ_ASSIGNMENT_RECOMMENDATIONS", "ASSIGNMENT_RECOMMENDATION", ticket_id
    )
    return result
