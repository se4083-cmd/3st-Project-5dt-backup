"""Synchronous, idempotent VOC drafts from immutable published aggregates only."""

from uuid import uuid4

from sqlalchemy import and_, exists, or_, select, update

from app import analytics_views, audit, automation_control, repository
from app.analytics_canonical import digest, normalize
from app.db import utcnow
from app.errors import APIError
from app.models import products, users

from . import voc_provider
from .models import p1_idempotency
from .permissions import allowed_teams
from .voc_models import voc_requests as requests
from .voc_models import voc_reviews as reviews
from .voc_models import voc_teams as teams


def authorize(session, user, permission, selected=None, lock=False):
    if lock:
        current = (
            session.execute(select(users).where(users.c.user_id == user["user_id"]).with_for_update())
            .mappings()
            .one()
        )
        if not current["active"]:
            raise APIError(401, "INVALID_CREDENTIALS")
        user = current
    automation_control.capability(session, user, permission, admin=True)
    return allowed_teams(session, user, selected)


def visible(allowed):
    return ~exists(
        select(1).where(teams.c.request_id == requests.c.request_id, teams.c.team_id.not_in(allowed))
    )


def row_for(session, identifier, allowed):
    row = (
        session.execute(select(requests).where(requests.c.request_id == identifier, visible(allowed)))
        .mappings()
        .first()
    )
    if row is None:
        raise APIError(404, "VOC_PROPOSAL_NOT_FOUND")
    return row


def view(session, row):
    result = dict(row)
    result["team_ids"] = sorted(
        session.scalars(select(teams.c.team_id).where(teams.c.request_id == row["request_id"]))
    )
    result["reviews"] = [
        dict(r)
        for r in session.execute(
            select(reviews)
            .where(reviews.c.request_id == row["request_id"])
            .order_by(reviews.c.created_at, reviews.c.review_id)
        ).mappings()
    ]
    for r in result["reviews"]:
        r.pop("request_id")
    return result


def replay(session, user, operation, key, hash_):
    row = (
        session.execute(
            select(p1_idempotency).where(
                p1_idempotency.c.user_id == user["user_id"],
                p1_idempotency.c.operation == operation,
                p1_idempotency.c.key == key,
            )
        )
        .mappings()
        .first()
    )
    if row:
        if row["request_hash"] != hash_:
            raise APIError(409, "IDEMPOTENCY_KEY_CONFLICT")
        return row["response_snapshot"]


def remember(session, user, operation, key, hash_, result, *, response_status=None):
    session.execute(
        p1_idempotency.insert().values(
            user_id=user["user_id"],
            operation=operation,
            key=key,
            request_hash=hash_,
            response_status=response_status
            if response_status is not None
            else (201 if operation == "VOC_GENERATE" else 200),
            response_snapshot=normalize(result),
            created_at=utcnow(),
        )
    )


def evidence_for(session, user, settings, product_id, selected):
    session.info["snapshot_as_of"] = utcnow()
    snapshot = analytics_views.resolve_snapshot(session, user, settings, selected)
    evidence = {
        "meta": normalize(snapshot["meta"]),
        "product_id": product_id,
        "score_meaning": "MANAGEMENT_PRIORITY_NOT_DEFECT_RATE_OR_CONFIRMED_DEFECT",
        "fabric_connection": "UNVERIFIED",
        "method_version": "voc-proposal-v1",
    }
    if snapshot["availability"] != "AVAILABLE":
        return evidence, snapshot["reason"], None
    bid = snapshot["batch_id"]
    if snapshot["meta"]["stale"]:
        return evidence, "STALE_ANALYTICS", bid
    detail = analytics_views.product_detail(session, snapshot, product_id)
    risk = detail["product"].model_dump(mode="json")
    trend = [r.model_dump(mode="json") for r in detail["trend"]]
    m = risk["metrics"]
    evidence["facts"] = {
        "risk": {
            "score": risk["score"],
            "risk_band": risk["risk_band"],
            "data_status": risk["data_status"],
            "rule_version": risk["rule_version"],
        },
        "repeat": {
            "C": m["C"],
            "M": m["M"],
            "K": m["K"],
            "top_issue": m["top_issue"],
            "issue_concentration": m["M"] / m["C"] if m["C"] else None,
            "meaning": "C=recent VOC episodes; M=largest primary-issue episode count; K=distinct customers. Concentration is not repeat-contact frequency or confirmed defect rate",
        },
        "rate": {
            "N": m["N"],
            "S": m["S"],
            "raw_rate": m["raw_rate"],
            "smoothed_rate": m["smoothed_rate"],
            "denominator_scope": snapshot["meta"]["sales_denominator_scope"],
            "cohort_inquiry_ratio": m["N"] / m["S"] if m["S"] else None,
            "meaning": "N=distinct recent complaint orders in paid sales cohort; S=global product paid orders, 28d. raw_rate/smoothed_rate are upstream published values, not recomputed",
        },
        "trend": {
            "recent_count": m["C"],
            "prior_count": m["P"],
            "growth": m["growth"],
            "windows": normalize(snapshot["meta"]["windows"]),
            "daily": trend,
        },
    }
    reason = None
    if risk["data_status"] != "ELIGIBLE":
        reason = risk["data_status"]
    elif not all(
        m[k] for k in ("sales_complete", "quality_ok", "complaints_complete", "episode_state_complete")
    ):
        reason = "INCOMPLETE_ANALYTICS"
    elif m["S"] < 30 or m["C"] < 5 or m["K"] < 3 or m["raw_rate"] is None or m["top_issue"] is None:
        reason = "LOW_SAMPLE"
    elif len({r["day"] for r in trend}) < 2:
        reason = "INSUFFICIENT_TREND"
    return evidence, reason, bid


def generate(session, user, body, key, app_settings, config):
    selected = authorize(session, user, "P1_VOC_GENERATE", body.team_ids, lock=True)
    fingerprint = digest({"product_id": body.product_id, "team_ids": selected})
    previous = replay(session, user, "VOC_GENERATE", key, fingerprint)
    if previous:
        return previous, True
    pid = str(body.product_id)
    if not session.scalar(select(products.c.product_id).where(products.c.product_id == pid)):
        raise APIError(404, "PRODUCT_NOT_FOUND")
    evidence, reason, bid = evidence_for(session, user, app_settings, pid, selected)
    proposal, deployment = None, None
    status = "INSUFFICIENT_DATA" if reason else "PENDING_REVIEW"
    if reason is None:
        try:
            proposal = voc_provider.generate(config, evidence)
            if config.provider == "AZURE_OPENAI":
                deployment = config.azure_deployment
        except voc_provider.ProviderFailure as exc:
            status, reason = "FAILED", exc.code
        # Recheck current SQL grants after the bounded provider call.
        authorize(session, user, "P1_VOC_GENERATE", selected)
    identifier = str(uuid4())
    session.execute(
        requests.insert().values(
            request_id=identifier,
            product_id=pid,
            batch_id=bid,
            created_by=user["user_id"],
            status=status,
            provider=config.provider,
            model_deployment=deployment,
            evidence=evidence,
            evidence_hash=digest(evidence),
            proposal=proposal,
            reason_code=reason,
        )
    )
    session.execute(teams.insert(), [{"request_id": identifier, "team_id": t} for t in selected])
    audit.record(
        session,
        user["user_id"],
        "GENERATE_VOC_PROPOSAL",
        "P1_VOC_REQUEST",
        identifier,
        result="SUCCESS" if proposal else "FAILURE",
        reason=reason or "DRAFT_REQUIRES_REVIEW",
    )
    result = view(session, row_for(session, identifier, selected))
    remember(session, user, "VOC_GENERATE", key, fingerprint, result)
    return result, False


def detail(session, user, identifier):
    allowed = authorize(session, user, "P1_VOC_READ")
    audit.record(session, user["user_id"], "READ_VOC_PROPOSAL", "P1_VOC_REQUEST", identifier)
    return view(session, row_for(session, identifier, allowed))


def history(session, user, limit, cursor=None, product_id=None):
    allowed = authorize(session, user, "P1_VOC_READ")
    query = select(requests).where(visible(allowed))
    if product_id:
        query = query.where(requests.c.product_id == str(product_id))
    if cursor:
        at, identifier = repository.decode_cursor(cursor)
        query = query.where(
            or_(
                requests.c.created_at < at,
                and_(requests.c.created_at == at, requests.c.request_id < identifier),
            )
        )
    rows = list(
        session.execute(
            query.order_by(requests.c.created_at.desc(), requests.c.request_id.desc()).limit(limit + 1)
        ).mappings()
    )
    items = [view(session, row) for row in rows[:limit]]
    audit.record(session, user["user_id"], "READ_VOC_HISTORY", "P1_VOC_REQUEST", None)
    return {
        "items": items,
        "next_cursor": repository.encode_cursor(items[-1]["created_at"], items[-1]["request_id"])
        if len(rows) > limit
        else None,
    }


def review(session, user, identifier, body, key):
    allowed = authorize(session, user, "P1_VOC_REVIEW", lock=True)
    row_for(session, identifier, allowed)
    fingerprint = digest({"request_id": identifier, **body.model_dump()})
    previous = replay(session, user, "VOC_REVIEW", key, fingerprint)
    if previous:
        return previous, True
    changed = session.execute(
        update(requests)
        .where(
            requests.c.request_id == identifier,
            requests.c.status == "PENDING_REVIEW",
            requests.c.revision == body.expected_revision,
        )
        .values(status=body.decision, revision=requests.c.revision + 1, updated_at=utcnow())
    )
    if changed.rowcount != 1:
        raise APIError(409, "VOC_REVIEW_CONFLICT")
    session.execute(
        reviews.insert().values(
            review_id=str(uuid4()),
            request_id=identifier,
            reviewed_by=user["user_id"],
            decision=body.decision,
            reason=body.reason,
        )
    )
    audit.record(
        session, user["user_id"], "REVIEW_VOC_PROPOSAL", "P1_VOC_REQUEST", identifier, reason=body.decision
    )
    result = view(session, row_for(session, identifier, allowed))
    remember(session, user, "VOC_REVIEW", key, fingerprint, result)
    return result, False
