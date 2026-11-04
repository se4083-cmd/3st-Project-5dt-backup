"""Read-only SQL aggregates, using the same snapshot and ticket predicate as P0."""

from sqlalchemy import and_, case, func, or_, select

from app import analytics_views, automation_control, repository
from app.models import automation_jobs as jobs
from app.models import tickets
from app.resolution import WorkRejected
from app.staff_router import ControlState

from .permissions import capabilities

STATUSES = ("PENDING", "RUNNING", "RETRY", "SUCCEEDED", "FAILED", "HANDED_OFF", "CANCELLED")
SAFE_ERRORS = {
    "AUTOMATION_PAUSED",
    "AUTOMATION_GENERATION_CHANGED",
    "LEASE_EXPIRED",
    "MAX_ATTEMPTS",
    "TIMEOUT",
    "RATE_LIMITED",
    "PROVIDER_UNAVAILABLE",
}


def predicate(user, team_ids, job_kind=None):
    terms = [repository.ticket_scope(user), tickets.c.team_id.in_(team_ids)]
    if job_kind:
        terms.append(jobs.c.job_kind == job_kind)
    return and_(*terms)


def current():
    return and_(jobs.c.cycle_no == tickets.c.cycle_no, jobs.c.expected_ticket_version == tickets.c.version)


def summary(session, user, settings, team_ids, job_kind=None):
    now = session.info["snapshot_as_of"]
    try:
        state = automation_control.read_control(session)
    except WorkRejected:
        state = None
    grants = capabilities(session, user)
    if "AUTOMATION_READ" not in grants:
        automation = dict(availability="UNAVAILABLE", state=None, reason="PERMISSION_REQUIRED")
    elif state is None:
        automation = dict(availability="UNAVAILABLE", state=None, reason="AUTOMATION_CONTROL_UNAVAILABLE")
    else:
        automation = dict(
            availability="AVAILABLE", state={k: state[k] for k in ControlState.model_fields}, reason=None
        )
    source = jobs.join(tickets, jobs.c.ticket_id == tickets.c.ticket_id)
    scope = predicate(user, team_ids, job_kind)
    raw = {
        kind: dict.fromkeys(STATUSES, 0) for kind in ("AUTO", "HANDOFF") if not job_kind or kind == job_kind
    }
    for kind, status, count in session.execute(
        select(jobs.c.job_kind, jobs.c.status, func.count())
        .select_from(source)
        .where(scope)
        .group_by(jobs.c.job_kind, jobs.c.status)
    ):
        raw[kind][status] = count
    pending = and_(current(), jobs.c.status == "PENDING", jobs.c.next_attempt_at <= now)
    # Eligibility is not a promise that a worker can claim it (ticket policy still applies).
    if state is not None:
        pending = and_(
            pending,
            or_(
                jobs.c.job_kind == "HANDOFF",
                and_(jobs.c.automation_generation == state["generation"], not state["paused"]),
            ),
        )
    else:
        pending = and_(pending, jobs.c.job_kind == "HANDOFF")
    definitions = dict(
        eligible_pending=pending,
        active_running=and_(current(), jobs.c.status == "RUNNING", jobs.c.lease_until > now),
        retry_wait=and_(current(), jobs.c.status == "RETRY"),
        expired_running=and_(current(), jobs.c.status == "RUNNING", jobs.c.lease_until <= now),
        superseded=~current(),
        current_failed=and_(current(), jobs.c.status == "FAILED"),
    )
    if state is not None:
        definitions["generation_mismatch"] = and_(
            current(),
            jobs.c.job_kind == "AUTO",
            jobs.c.status.in_(["PENDING", "RUNNING", "RETRY"]),
            jobs.c.automation_generation != state["generation"],
        )
    counts = dict(
        session.execute(
            select(*(func.count(case((p, 1))).label(k) for k, p in definitions.items()))
            .select_from(source)
            .where(scope)
        )
        .mappings()
        .one()
    )
    counts.setdefault("generation_mismatch", None)
    snapshot = analytics_views.resolve_snapshot(session, user, settings, team_ids)
    return dict(
        as_of=now,
        selected_team_ids=team_ids,
        excluded_definition="Unrouted/team NULL and unauthorized teams excluded; raw includes history. "
        "Current = matching ticket cycle AND version. Expired and generation mismatch may overlap; do not sum. "
        "Pending eligibility = due, current, generation-valid and not paused (AUTO); worker policy still applies.",
        automation=automation,
        jobs=dict(raw_counts=raw, **counts),
        p1_tasks={},
        analytics={k: snapshot[k] for k in ("availability", "reason", "meta")},
        ai={},
    )


def job_page(session, user, team_ids, *, job_kind=None, status=None, limit=20, cursor=None):
    scope = predicate(user, team_ids, job_kind)
    if status:
        scope = and_(scope, jobs.c.status == status)
    query = (
        select(jobs, current().label("is_current"))
        .select_from(jobs.join(tickets, jobs.c.ticket_id == tickets.c.ticket_id))
        .where(scope)
    )
    if cursor:
        at, identifier = repository.decode_cursor(cursor)
        query = query.where(
            or_(jobs.c.updated_at < at, and_(jobs.c.updated_at == at, jobs.c.job_id < identifier))
        )
    rows = list(
        session.execute(
            query.order_by(jobs.c.updated_at.desc(), jobs.c.job_id.desc()).limit(limit + 1)
        ).mappings()
    )
    items = []
    for r in rows[:limit]:
        item = {
            k: r[k]
            for k in (
                "job_id",
                "ticket_id",
                "job_kind",
                "status",
                "attempt",
                "next_attempt_at",
                "updated_at",
                "cycle_no",
                "expected_ticket_version",
                "data_origin",
            )
        }
        item.update(
            lease_expires_at=r["lease_until"],
            scope_status="CURRENT" if r["is_current"] else "SUPERSEDED",
            error_code=r["error_code"]
            if r["error_code"] in SAFE_ERRORS
            else ("UNKNOWN_ERROR" if r["error_code"] else None),
        )
        items.append(item)
    next_cursor = (
        repository.encode_cursor(items[-1]["updated_at"], items[-1]["job_id"]) if len(rows) > limit else None
    )
    return dict(
        as_of=session.info["snapshot_as_of"], selected_team_ids=team_ids, items=items, next_cursor=next_cursor
    )
