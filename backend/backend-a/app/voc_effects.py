"""Fabric supplies aggregates. A checks the contract, never recomputes VOC sources."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import audit
from app import voc_improvements as voc
from app.analytics_canonical import digest, normalize
from app.db import utcnow
from app.effect_models import effect_batches as batches
from app.effect_models import effect_current as pointer
from app.effect_schemas import EffectPayload
from app.errors import APIError, denied
from app.voc_models import plan_teams, plans, profiles


def status(session, batch_id):
    row = session.execute(select(batches).where(batches.c.batch_id == batch_id)).mappings().first()
    if not row:
        raise APIError(404, "EFFECT_BATCH_NOT_FOUND")
    return {k: row[k] for k in ("batch_id", "status", "validation")}


def event(session, identity, action, batch_id):
    audit.record(session, None, action, "VOC_EFFECT_BATCH", batch_id, service=identity["id"])


def receive(session, submission, identity, settings):
    p = submission.payload
    if p.origin == "OPERATIONAL" and identity["id"] not in settings.voc_effect_operational_ids:
        raise APIError(403, "EFFECT_OPERATIONAL_SOURCE_NOT_ALLOWED")
    value = normalize(p)
    hashed = digest(value)
    if hashed != submission.payload_sha256:
        raise APIError(422, "EFFECT_HASH_MISMATCH")
    if not session.scalar(select(profiles.c.action_id).where(profiles.c.action_id == str(p.action_id))):
        raise APIError(404, "EFFECT_PLAN_NOT_FOUND")
    if not session.scalar(
        select(plans.c.revision).where(
            plans.c.action_id == str(p.action_id), plans.c.revision == p.plan_revision
        )
    ):
        raise APIError(404, "EFFECT_PLAN_NOT_FOUND")
    try:
        with session.begin_nested():
            session.execute(
                batches.insert().values(
                    batch_id=str(submission.batch_id),
                    action_id=str(p.action_id),
                    plan_revision=p.plan_revision,
                    origin=p.origin,
                    source_as_of=p.source_as_of,
                    generated_at=p.generated_at,
                    content_hash=hashed,
                    payload=value,
                    status="RECEIVED",
                    validation={"passed": False, "codes": ["NOT_VALIDATED"]},
                    received_at=utcnow(),
                )
            )
            event(session, identity, "VOC_EFFECT_RECEIVED", str(submission.batch_id))
    except IntegrityError:
        old = (
            session.execute(select(batches).where(batches.c.batch_id == str(submission.batch_id)))
            .mappings()
            .first()
        )
        if not old or old["content_hash"] != hashed:
            raise APIError(409, "EFFECT_BATCH_CONTENT_CONFLICT") from None
    return status(session, str(submission.batch_id))


def validation(session, row):
    p = EffectPayload.model_validate(row["payload"])
    plan = (
        session.execute(
            select(plans).where(
                plans.c.action_id == row["action_id"], plans.c.revision == row["plan_revision"]
            )
        )
        .mappings()
        .one()
    )
    profile = (
        session.execute(select(profiles).where(profiles.c.action_id == row["action_id"])).mappings().one()
    )
    action, _ = None, None
    from app.models import followup_actions

    action = (
        session.execute(select(followup_actions).where(followup_actions.c.action_id == row["action_id"]))
        .mappings()
        .one()
    )
    codes, warnings = [], []
    if row["content_hash"] != digest(normalize(p)):
        codes.append("STORED_HASH_MISMATCH")
    if profile["product_id"] != str(p.product_id):
        codes.append("PRODUCT_MISMATCH")
    if p.issue_code != plan["issue_code"]:
        codes.append("ISSUE_MISMATCH")
    if profile["current_plan_revision"] != p.plan_revision:
        codes.append("PLAN_NOT_CURRENT")
    if action["owner_team_id"] != plan["owner_team_id_snapshot"]:
        codes.append("OWNER_TEAM_CHANGED_RECONFIRM_PLAN")
    for field in ("implemented_at", "before_start", "before_end", "after_start", "after_end"):
        if getattr(p, field) != plan[field]:
            codes.append("PLAN_WINDOW_MISMATCH")
            break
    teams = set(
        session.scalars(
            select(plan_teams.c.team_id).where(
                plan_teams.c.action_id == row["action_id"], plan_teams.c.revision == row["plan_revision"]
            )
        )
    )
    if teams != {str(t) for t in p.scope_team_ids}:
        codes.append("EXACT_SCOPE_MISMATCH")
    if not p.source_as_of <= p.generated_at <= utcnow() + timedelta(minutes=5):
        codes.append("INVALID_SOURCE_TIME")
    if p.source_as_of < p.after_end:
        warnings.append("OBSERVATION_IMMATURE")
    if p.before_definition != p.after_definition:
        warnings.append("DEFINITION_CHANGED")
    if p.overlap != "NONE_REPORTED":
        warnings.append("OVERLAP_REPORTED" if p.overlap == "POSSIBLE" else "OVERLAP_UNKNOWN")

    def equal(actual, expected):
        return (
            actual is None
            if expected is None
            else actual is not None and abs(Decimal(actual) - expected) <= Decimal("0.000000001")
        )

    rates = []
    for period in (p.before, p.after):
        complete = period.inquiry_coverage == 1 and period.inquiry_count is not None
        if not complete:
            warnings.append("SOURCE_INCOMPLETE")
        expected = (
            Decimal(period.inquiry_count) / Decimal(period.sales_count)
            if (
                complete
                and period.sales_coverage == 1
                and period.sales_count is not None
                and period.sales_count > 0
            )
            else None
        )
        if not equal(period.inquiries_per_sale, expected):
            codes.append("INQUIRY_RATE_INVALID")
        if period.sales_count == 0 and period.sales_coverage == 1:
            warnings.append("ZERO_SALES_DENOMINATOR")
        if period.sales_count is None or period.sales_coverage != 1:
            warnings.append("SALES_DENOMINATOR_UNAVAILABLE")
        rates.append(expected)
    comparable = p.before_definition == p.after_definition and all(
        x.inquiry_coverage == 1 and x.inquiry_count is not None for x in (p.before, p.after)
    )
    delta = Decimal(p.after.inquiry_count - p.before.inquiry_count) if comparable else None
    relative = delta / Decimal(p.before.inquiry_count) if comparable and p.before.inquiry_count else None
    rate_delta = rates[1] - rates[0] if comparable and None not in rates else None
    rate_relative = rate_delta / rates[0] if rate_delta is not None and rates[0] else None
    for supplied, expected in [
        (p.count_absolute_change, delta),
        (p.count_relative_change, relative),
        (p.rate_absolute_change, rate_delta),
        (p.rate_relative_change, rate_relative),
    ]:
        if not equal(supplied, expected):
            codes.append("CHANGE_ARITHMETIC_INVALID")
    if comparable and p.before.inquiry_count == 0:
        warnings.append("ZERO_BEFORE_BASELINE")
    return {
        "passed": not codes,
        "codes": sorted(set(codes)),
        "status_codes": sorted(set(warnings)),
        "comparison_basis": "INQUIRIES_PER_SALE"
        if rate_delta is not None
        else "INQUIRY_COUNT"
        if delta is not None
        else "UNAVAILABLE",
    }


def lock(session, batch_id):
    hint = session.execute(select(batches).where(batches.c.batch_id == batch_id)).mappings().first()
    if not hint:
        raise APIError(404, "EFFECT_BATCH_NOT_FOUND")
    session.execute(select(profiles).where(profiles.c.action_id == hint["action_id"]).with_for_update()).one()
    return (
        session.execute(select(batches).where(batches.c.batch_id == batch_id).with_for_update())
        .mappings()
        .one()
    )


def validate(session, batch_id, identity):
    row = lock(session, batch_id)
    if row["status"] != "RECEIVED":
        return status(session, batch_id)
    result = validation(session, row)
    session.execute(
        batches.update()
        .where(batches.c.batch_id == batch_id)
        .values(validation=result, status="VALIDATED" if result["passed"] else "FAILED")
    )
    event(session, identity, "VOC_EFFECT_VALIDATED", batch_id)
    return status(session, batch_id)


def publish(session, batch_id, identity):
    row = lock(session, batch_id)
    if row["status"] == "SUCCEEDED":
        return status(session, batch_id)  # Never repromote an old success.
    if row["status"] != "VALIDATED" or not row["validation"]["passed"]:
        raise APIError(409, "EFFECT_BATCH_NOT_VALIDATED")
    result = validation(session, row)
    if not result["passed"]:
        raise APIError(409, "EFFECT_PLAN_OR_CONTENT_CHANGED")
    pred = (
        pointer.c.action_id == row["action_id"],
        pointer.c.plan_revision == row["plan_revision"],
        pointer.c.origin == row["origin"],
    )
    old_id = session.scalar(select(pointer.c.batch_id).where(*pred))
    if old_id:
        old = session.execute(select(batches).where(batches.c.batch_id == old_id)).mappings().one()
        if (
            row["source_as_of"] < old["source_as_of"]
            or row["generated_at"] < old["generated_at"]
            or (row["source_as_of"] == old["source_as_of"] and row["generated_at"] == old["generated_at"])
        ):
            raise APIError(409, "EFFECT_BATCH_NOT_NEWER")
    with session.begin_nested():
        session.execute(
            batches.update()
            .where(batches.c.batch_id == batch_id)
            .values(status="SUCCEEDED", published_at=utcnow())
        )
        if old_id:
            session.execute(pointer.update().where(*pred).values(batch_id=batch_id))
        else:
            session.execute(
                pointer.insert().values(
                    action_id=row["action_id"],
                    plan_revision=row["plan_revision"],
                    origin=row["origin"],
                    batch_id=batch_id,
                )
            )
        event(session, identity, "VOC_EFFECT_PUBLISHED", batch_id)
    return status(session, batch_id)


def view(session, user, action_id, plan_revision=None, origin="OPERATIONAL"):
    voc.authorize(session, user)
    action, profile = voc.action_for(session, user, action_id)
    revision = plan_revision or profile["current_plan_revision"]
    plan = voc.plan_for(session, user, action_id, revision)
    if not plan:
        raise denied(user["user_id"], "VOC_EFFECT_PLAN", action_id)
    now = session.info["snapshot_as_of"]
    base = dict(as_of=now, origin=origin, plan_is_current=revision == profile["current_plan_revision"])
    if plan["owner_team_id_snapshot"] != action["owner_team_id"]:
        return dict(**base, availability="UNAVAILABLE", reason="PLAN_RECONFIRM_REQUIRED")
    row = (
        session.execute(
            select(batches)
            .join(pointer, pointer.c.batch_id == batches.c.batch_id)
            .where(
                pointer.c.action_id == action_id,
                pointer.c.plan_revision == revision,
                pointer.c.origin == origin,
            )
        )
        .mappings()
        .first()
    )
    audit.record(session, user["user_id"], "VOC_EFFECT_READ", "VOC_IMPROVEMENT", action_id)
    if not row:
        return dict(**base, availability="UNAVAILABLE", reason="NO_PUBLISHED_EFFECT_BATCH")
    return dict(
        **base,
        availability="AVAILABLE",
        reason="UPSTREAM_RESULT_NOT_CAUSAL_PROOF",
        batch_id=row["batch_id"],
        status_codes=row["validation"]["status_codes"],
        payload=row["payload"],
    )
