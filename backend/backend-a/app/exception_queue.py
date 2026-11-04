"""Queue visibility is an independent, explicit routing capability, not ticket access."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import and_, case, exists, func, or_, select

from app import audit, repository
from app.automation_control import capability, read_control
from app.db import utcnow
from app.errors import APIError
from app.model_constraints import team_categories, user_team_scopes
from app.models import automation_jobs as jobs
from app.models import teams, tickets
from app.resolution import WorkRejected
from app.schemas import Input
from app.services import STAGES
from app.staff_models import queue_routes as routes

QueueScope = Literal["ROUTED", "UNROUTED"]
QueueReason = Literal["UNASSIGNED", "AUTO_FAILED", "ROUTING_FAILED", "HUMAN_REQUEST"]


class QueueItem(BaseModel):
    ticket_id: UUID
    cycle_no: int
    route_team_id: UUID | None
    reason_code: QueueReason
    stage: str
    queued_at: datetime
    waiting_seconds: int
    job_state: str | None
    automatic_state: Literal[
        "PAUSED",
        "RECLAIM_REQUIRED",
        "READY",
        "HUMAN_REVIEW_REQUIRED",
        "NOT_APPLICABLE",
        "CONTROL_UNAVAILABLE",
    ]


class QueuePage(BaseModel):
    items: list[QueueItem]
    next_cursor: str | None
    total: int
    counts: dict[str, int]
    as_of: datetime


class RouteCommand(Input):
    expected_revision: int = Field(ge=1)
    cycle_no: int = Field(ge=1)
    expected_route_revision: int = Field(ge=0)
    team_id: UUID | None


def record_queue_route(session, ticket_id, body: RouteCommand, *, service_id):
    """Trusted B DB boundary; caller authenticates service and commits its whole transaction.

    Does not choose a team, assign anyone, alter ticket revision or grant access.
    Call before taking any job locks, or while retaining the ticket lock.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", service_id):
        raise ValueError("INVALID_SERVICE_ID")
    ticket = (
        session.execute(select(tickets).where(tickets.c.ticket_id == ticket_id).with_for_update())
        .mappings()
        .first()
    )
    if not ticket or ticket["cycle_no"] != body.cycle_no or ticket["version"] != body.expected_revision:
        raise APIError(409, "ROUTE_TICKET_REVISION_CONFLICT")
    if ticket["status"] in {"RESOLVED", "CANCELLED"}:
        raise APIError(409, "ROUTE_TICKET_FINISHED")
    team_id = str(body.team_id) if body.team_id else None
    if team_id and not session.scalar(
        select(teams.c.team_id).where(teams.c.team_id == team_id, teams.c.active.is_(True))
    ):
        raise APIError(409, "ROUTE_TEAM_UNAVAILABLE")
    predicate = and_(routes.c.ticket_id == ticket_id, routes.c.cycle_no == body.cycle_no)
    old = session.execute(select(routes).where(predicate)).mappings().first()
    if (old["revision"] if old else 0) != body.expected_route_revision:
        raise APIError(409, "ROUTE_REVISION_CONFLICT")
    values = dict(
        team_id=team_id,
        revision=body.expected_route_revision + 1,
        recorded_by_service=service_id,
        recorded_at=utcnow(),
    )
    with session.begin_nested():
        if old:
            session.execute(routes.update().where(predicate).values(**values))
        else:
            session.execute(routes.insert().values(ticket_id=ticket_id, cycle_no=body.cycle_no, **values))
        audit.record(
            session,
            None,
            "QUEUE_ROUTE_RECORDED",
            "TICKET",
            ticket_id,
            ticket=ticket_id,
            cycle=body.cycle_no,
            service=service_id,
        )
        from app.automation_monitor import record

        record(
            session,
            ticket_id,
            body.cycle_no,
            "ROUTED",
            ticket["version"],
            key=f"ROUTE_{values['revision']}",
            team_id=team_id,
        )
    return {"ticket_id": ticket_id, "cycle_no": body.cycle_no, **values}


def queue_query(session, user, scope, reason=None, team_id=None):
    capability(
        session,
        user,
        "UNROUTED_QUEUE_READ" if scope == "UNROUTED" else "EXCEPTION_QUEUE_READ",
        admin=scope == "UNROUTED",
    )
    join = tickets.outerjoin(
        routes, and_(routes.c.ticket_id == tickets.c.ticket_id, routes.c.cycle_no == tickets.c.cycle_no)
    ).outerjoin(jobs, and_(jobs.c.ticket_id == tickets.c.ticket_id, jobs.c.cycle_no == tickets.c.cycle_no))
    assigned = repository.agent_assignment_exists()
    why = case(
        (and_(jobs.c.status == "FAILED", jobs.c.job_kind == "AUTO"), "AUTO_FAILED"),
        (and_(jobs.c.status == "FAILED", jobs.c.job_kind == "HANDOFF"), "ROUTING_FAILED"),
        (and_(jobs.c.job_kind == "HANDOFF", jobs.c.source_message_id.is_not(None)), "HUMAN_REQUEST"),
        else_="UNASSIGNED",
    )
    predicate = and_(
        tickets.c.status.not_in(["RESOLVED", "CANCELLED"]), or_(~assigned, jobs.c.status == "FAILED")
    )
    if scope == "UNROUTED":
        if team_id:
            raise APIError(422, "UNROUTED_TEAM_FILTER_NOT_ALLOWED")
        active_route = exists(
            select(1).where(teams.c.team_id == routes.c.team_id, teams.c.active.is_(True))
        ).correlate(routes)
        predicate = and_(predicate, or_(routes.c.team_id.is_(None), ~active_route))
    else:
        allowed = exists(
            select(1)
            .select_from(user_team_scopes.join(teams))
            .where(
                user_team_scopes.c.user_id == user["user_id"],
                user_team_scopes.c.team_id == routes.c.team_id,
                teams.c.active.is_(True),
            )
        ).correlate(routes)
        predicate = and_(predicate, routes.c.team_id.is_not(None), allowed)
        if user["role"] == "AGENT":
            predicate = and_(
                predicate,
                routes.c.team_id == user["team_id"],
                exists(
                    select(1).where(
                        team_categories.c.team_id == routes.c.team_id,
                        team_categories.c.category == tickets.c.category,
                    )
                ).correlate(routes, tickets),
            )
        if team_id:
            # Reject unauthorized filters rather than returning a global fallback.
            if not session.scalar(
                select(user_team_scopes.c.team_id)
                .join(teams)
                .where(
                    user_team_scopes.c.user_id == user["user_id"],
                    user_team_scopes.c.team_id == team_id,
                    teams.c.active.is_(True),
                )
            ) or (user["role"] == "AGENT" and team_id != user["team_id"]):
                raise APIError(403, "QUEUE_TEAM_SCOPE_DENIED", user["user_id"])
            predicate = and_(predicate, routes.c.team_id == team_id)
    if reason:
        predicate = and_(predicate, why == reason)
    return join, predicate, why


def view(
    session, user, *, scope="ROUTED", reason=None, team_id=None, limit=20, cursor=None, counts_only=False
):
    join, predicate, why = queue_query(session, user, scope, reason, team_id)
    counts = dict(
        session.execute(
            select(why.label("reason"), func.count()).select_from(join).where(predicate).group_by(why)
        ).all()
    )
    result = {"total": sum(counts.values()), "counts": counts, "as_of": session.info["snapshot_as_of"]}
    if not counts_only:
        query = (
            select(
                tickets.c.ticket_id,
                tickets.c.cycle_no,
                tickets.c.status,
                tickets.c.created_at,
                routes.c.team_id.label("route_team_id"),
                func.coalesce(routes.c.recorded_at, jobs.c.created_at, tickets.c.updated_at).label(
                    "queued_at"
                ),
                why.label("reason_code"),
                jobs.c.status.label("job_state"),
                jobs.c.job_kind,
                jobs.c.automation_generation,
                jobs.c.lease_until,
            )
            .select_from(join)
            .where(predicate)
        )
        if cursor:
            timestamp, identifier = repository.decode_cursor(cursor)
            query = query.where(
                or_(
                    tickets.c.created_at < timestamp,
                    and_(tickets.c.created_at == timestamp, tickets.c.ticket_id < identifier),
                )
            )
        rows = list(
            session.execute(
                query.order_by(tickets.c.created_at.desc(), tickets.c.ticket_id.desc()).limit(limit + 1)
            ).mappings()
        )
        try:
            control = read_control(session)
        except WorkRejected:
            control = None
        items = []
        for r in rows[:limit]:
            state = "NOT_APPLICABLE"
            if r["job_kind"] == "AUTO":
                state = (
                    "CONTROL_UNAVAILABLE"
                    if control is None
                    else "HUMAN_REVIEW_REQUIRED"
                    if r["job_state"] == "FAILED"
                    else "PAUSED"
                    if control["paused"]
                    else "RECLAIM_REQUIRED"
                    if r["job_state"] == "RUNNING"
                    and (
                        r["automation_generation"] != control["generation"]
                        or r["lease_until"] <= session.info["snapshot_as_of"]
                    )
                    else "READY"
                )
            items.append(
                QueueItem(
                    ticket_id=r["ticket_id"],
                    cycle_no=r["cycle_no"],
                    route_team_id=r["route_team_id"] if scope == "ROUTED" else None,
                    reason_code=r["reason_code"],
                    stage=STAGES[r["status"]],
                    queued_at=r["queued_at"],
                    waiting_seconds=max(
                        0, int((session.info["snapshot_as_of"] - r["queued_at"]).total_seconds())
                    ),
                    job_state=r["job_state"],
                    automatic_state=state,
                )
            )
        result.update(
            items=items,
            next_cursor=repository.encode_cursor(rows[limit - 1]["created_at"], rows[limit - 1]["ticket_id"])
            if len(rows) > limit
            else None,
        )
    audit.record(session, user["user_id"], "READ_EXCEPTION_QUEUE", "QUEUE", None, reason=scope)
    return result
