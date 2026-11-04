"""Current repeatable-read cohort statistics. No historical as_of reconstruction."""

from sqlalchemy import and_, case, exists, func, or_, select

from app import audit
from app.automation_control import capability
from app.db import utcnow
from app.errors import APIError
from app.model_constraints import user_team_scopes
from app.models import messages, teams
from app.quality_models import reply_records as r
from app.quality_models import revisions as v
from app.quality_models import rubrics
from app.quality_models import samples as s


def allowed_teams(session, user):
    return set(
        session.scalars(
            select(user_team_scopes.c.team_id)
            .join(teams)
            .where(user_team_scopes.c.user_id == user["user_id"], teams.c.active.is_(True))
        )
    )


def aggregate(session, cohort, rubric):
    last = (
        select(v.c.sample_id, func.max(v.c.revision).label("rev"))
        .join(s, s.c.sample_id == v.c.sample_id)
        .where(v.c.event_kind == "REVIEW", v.c.revision <= s.c.current_revision)
        .group_by(v.c.sample_id)
        .subquery()
    )
    active = and_(s.c.sample_id.is_not(None), s.c.status != "VOID")
    reviewed = and_(active, v.c.revision.is_not(None))

    def count(p):
        return func.coalesce(func.sum(case((p, 1), else_=0)), 0)

    counters = {
        "active_sample_count": active,
        "void_count": s.c.status == "VOID",
        "reviewed_count": reviewed,
        "unreviewed_sample_count": and_(active, v.c.revision.is_(None)),
    }
    for field, column, codes in [
        ("accuracy", v.c.accuracy, ["CORRECT", "INCORRECT", "UNDETERMINABLE"]),
        ("policy", v.c.policy_alignment, ["MATCH", "MISMATCH", "UNDETERMINABLE", "NOT_APPLICABLE"]),
    ]:
        for code in codes:
            name = (
                code.lower()
                if field == "accuracy" and code != "UNDETERMINABLE"
                else field + "_" + code.lower()
            )
            counters[name] = and_(reviewed, column == code)
    row = (
        session.execute(
            select(
                func.count().label("confirmed_response_count"),
                *(count(p).label(k) for k, p in counters.items()),
            )
            .select_from(
                r.outerjoin(s, and_(s.c.message_id == r.c.message_id, s.c.rubric_version == rubric))
                .outerjoin(last, last.c.sample_id == s.c.sample_id)
                .outerjoin(v, and_(v.c.sample_id == last.c.sample_id, v.c.revision == last.c.rev))
            )
            .where(*cohort)
        )
        .mappings()
        .one()
    )
    x = dict(row)
    x["accuracy_denominator"] = x["correct"] + x["incorrect"]
    x["policy_denominator"] = x["policy_match"] + x["policy_mismatch"]
    x["accuracy_rate"] = x["correct"] / x["accuracy_denominator"] if x["accuracy_denominator"] else None
    x["policy_alignment_rate"] = (
        x["policy_match"] / x["policy_denominator"] if x["policy_denominator"] else None
    )
    x["evaluation_coverage"] = (
        x["reviewed_count"] / x["confirmed_response_count"] if x["confirmed_response_count"] else None
    )
    x["unreviewed_response_count"] = x["confirmed_response_count"] - x["reviewed_count"]
    x["unselected_or_void_response_count"] = x["confirmed_response_count"] - x["active_sample_count"]
    return x


def metrics(session, user, start, end, rubric, origin, team_ids, include_unattributed):
    capability(session, user, "QUALITY_METRICS_READ", admin=True)
    if not start < end or (end - start).days > 366:
        raise APIError(422, "QUALITY_PERIOD_INVALID")
    if not session.scalar(select(exists().where(rubrics.c.version == rubric))):
        raise APIError(422, "QUALITY_RUBRIC_UNKNOWN")
    allowed = allowed_teams(session, user)
    selected = set(map(str, team_ids)) if team_ids is not None else allowed
    if not selected <= allowed or (team_ids is not None and len(selected) != len(team_ids)):
        raise APIError(403, "QUALITY_TEAM_SCOPE_DENIED", user["user_id"])
    cohort = [r.c.committed_at >= start, r.c.committed_at < end, r.c.origin == origin]
    attributed = aggregate(session, [*cohort, r.c.attribution_team_id.in_(selected)], rubric)
    # These are workload/sample counts, never processing attribution or population coverage.
    review_scope = or_(r.c.attribution_team_id.is_not(None), False)
    if include_unattributed:
        capability(session, user, "QUALITY_UNATTRIBUTED_MANAGE", admin=True)
        if not selected:
            raise APIError(403, "QUALITY_TEAM_SCOPE_DENIED", user["user_id"])
        review_scope = True
    work = aggregate(session, [*cohort, s.c.review_team_id.in_(selected), review_scope], rubric)
    unattr = legacy = None
    if include_unattributed:
        unattr = session.scalar(
            select(func.count()).select_from(r).where(*cohort, r.c.attribution_team_id.is_(None))
        )
        legacy = session.scalar(
            select(func.count())
            .select_from(messages)
            .where(
                messages.c.direction == "OUT",
                messages.c.visibility == "PUBLIC",
                messages.c.final_reply,
                messages.c.created_at >= start,
                messages.c.created_at < end,
                (
                    messages.c.data_origin == origin
                    if origin != "UNKNOWN"
                    else messages.c.data_origin.not_in(["APPLICATION", "SYNTHETIC"])
                ),
                ~exists(select(1).where(r.c.message_id == messages.c.message_id)),
            )
        )
    audit.record(session, user["user_id"], "QUALITY_METRICS_READ", "QUALITY_METRICS", None)
    return dict(
        as_of=session.info.get("snapshot_as_of", utcnow()),
        response_start=start,
        response_end=end,
        team_ids=sorted(selected),
        origin=origin,
        rubric_version=rubric,
        attributed=attributed,
        review_team_sample_counts={
            "active_sample_count": work["active_sample_count"],
            "void_count": work["void_count"],
            "reviewed_count": work["reviewed_count"],
            "unreviewed_sample_count": work["unreviewed_sample_count"],
        },
        review_team_evaluation={
            k: work[k]
            for k in (
                "correct",
                "incorrect",
                "accuracy_undeterminable",
                "policy_match",
                "policy_mismatch",
                "policy_undeterminable",
                "policy_not_applicable",
                "accuracy_denominator",
                "policy_denominator",
                "accuracy_rate",
                "policy_alignment_rate",
            )
        },
        unattributed_confirmed_response_count=unattr,
        legacy_auto_unknown_count=legacy,
        unknown_counts_scope="GLOBAL_UNATTRIBUTED_EXPLICIT_PERMISSION"
        if include_unattributed
        else "NOT_REQUESTED",
    )
