"""Scoped, optimistic, idempotent policy review workspace without activation."""

import re
from uuid import uuid4

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.exc import IntegrityError

from app import audit, repository
from app.analytics_canonical import digest, normalize
from app.errors import APIError
from app.models import knowledge_documents

from . import policy_analysis
from .policy_models import policies
from .policy_models import policy_comparisons as comparisons
from .policy_models import policy_reviews as reviews
from .policy_models import policy_teams as teams
from .policy_models import policy_versions as versions
from .policy_schemas import PolicyDiff, PolicyImpact
from .voc_service import authorize, remember, replay


def visible(allowed):
    return ~exists(
        select(1).where(teams.c.policy_id == policies.c.policy_id, teams.c.team_id.not_in(allowed))
    )


def policy_for(session, identifier, allowed, lock=False):
    query = select(policies).where(policies.c.policy_id == identifier, visible(allowed))
    if lock:
        query = query.with_for_update()
    row = session.execute(query).mappings().first()
    if row is None:
        raise APIError(404, "POLICY_NOT_FOUND")
    return row


def version_for(session, policy_id, identifier):
    row = (
        session.execute(
            select(versions).where(versions.c.policy_id == policy_id, versions.c.version_id == identifier)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise APIError(404, "POLICY_VERSION_NOT_FOUND")
    return row


def team_ids(session, policy_id):
    return sorted(session.scalars(select(teams.c.team_id).where(teams.c.policy_id == policy_id)))


def policy_view(session, row):
    rows = list(
        session.execute(
            select(versions)
            .where(versions.c.policy_id == row["policy_id"])
            .order_by(versions.c.version_no.desc())
            .limit(101)
        ).mappings()
    )
    return dict(
        row,
        team_ids=team_ids(session, row["policy_id"]),
        versions=[dict(r) for r in rows[:100]],
        versions_truncated=len(rows) > 100,
    )


def source_snapshot(session, body, policy_key):
    if body.source_document_id is None:
        return {}
    row = (
        session.execute(
            select(knowledge_documents)
            .where(knowledge_documents.c.document_id == str(body.source_document_id))
            .with_for_update(read=True)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise APIError(404, "POLICY_SOURCE_NOT_FOUND")
    if not re.fullmatch(r"[a-f0-9]{64}", row["content_hash"]):
        raise APIError(409, "POLICY_SOURCE_UNVERIFIABLE")
    text = row["body"].replace("\r\n", "\n").replace("\r", "\n")
    if row["policy_key"] != policy_key or text != body.body:
        raise APIError(409, "POLICY_SOURCE_MISMATCH")
    return dict(
        document_id=row["document_id"],
        version=row["version"],
        content_hash=row["content_hash"],
        body_hash=digest(text),
        policy_key=row["policy_key"],
        origin=row["data_origin"],
        verification="LOCAL_RECORD_MATCH_NOT_EXTERNAL_RAG_VERIFICATION",
    )


def insert_version(session, policy_id, number, body, user, key):
    source = source_snapshot(session, body, key)
    identifier = str(uuid4())
    session.execute(
        versions.insert().values(
            version_id=identifier,
            policy_id=policy_id,
            version_no=number,
            title=body.title,
            body=body.body,
            content_hash=digest({"title": body.title, "body": body.body}),
            source_document_id=str(body.source_document_id) if body.source_document_id else None,
            source_snapshot=source,
            created_by=user["user_id"],
        )
    )
    return dict(version_for(session, policy_id, identifier))


def register(session, user, body, key):
    selected = authorize(session, user, "P1_POLICY_WRITE", body.team_ids, lock=True)
    fingerprint = digest({**body.model_dump(), "team_ids": selected, "action": "REGISTER"})
    previous = replay(session, user, "POLICY_REGISTER", key, fingerprint)
    if previous:
        return previous, True
    identifier = str(uuid4())
    try:
        with session.begin_nested():
            session.execute(
                policies.insert().values(
                    policy_id=identifier,
                    policy_key=body.policy_key,
                    scope_hash=digest(selected),
                    latest_version=1,
                    created_by=user["user_id"],
                )
            )
    except IntegrityError:
        raise APIError(409, "POLICY_SCOPE_KEY_CONFLICT") from None
    session.execute(teams.insert(), [{"policy_id": identifier, "team_id": t} for t in selected])
    insert_version(session, identifier, 1, body, user, body.policy_key)
    result = policy_view(session, policy_for(session, identifier, selected))
    remember(session, user, "POLICY_REGISTER", key, fingerprint, result, response_status=201)
    audit.record(session, user["user_id"], "REGISTER_POLICY_VERSION", "P1_POLICY", identifier)
    return result, False


def append(session, user, identifier, body, key):
    allowed = authorize(session, user, "P1_POLICY_WRITE", lock=True)
    policy = policy_for(session, identifier, allowed, lock=True)
    fingerprint = digest({"action": "APPEND", "policy_id": identifier, **body.model_dump()})
    previous = replay(session, user, "POLICY_REGISTER", key, fingerprint)
    if previous:
        return previous, True
    if policy["latest_version"] != body.expected_previous_version:
        raise APIError(409, "POLICY_VERSION_CONFLICT")
    number = policy["latest_version"] + 1
    result = insert_version(session, identifier, number, body, user, policy["policy_key"])
    session.execute(update(policies).where(policies.c.policy_id == identifier).values(latest_version=number))
    remember(session, user, "POLICY_REGISTER", key, fingerprint, result, response_status=201)
    audit.record(session, user["user_id"], "REGISTER_POLICY_VERSION", "P1_POLICY", identifier)
    return result, False


def detail(session, user, identifier):
    allowed = authorize(session, user, "P1_POLICY_READ")
    result = policy_view(session, policy_for(session, identifier, allowed))
    audit.record(session, user["user_id"], "READ_POLICY", "P1_POLICY", identifier)
    return result


def version_page(session, user, identifier, limit, before=None):
    allowed = authorize(session, user, "P1_POLICY_READ")
    policy_for(session, identifier, allowed)
    query = select(versions).where(versions.c.policy_id == identifier)
    if before is not None:
        query = query.where(versions.c.version_no < before)
    rows = list(session.execute(query.order_by(versions.c.version_no.desc()).limit(limit + 1)).mappings())
    return dict(
        items=[dict(r) for r in rows[:limit]],
        next_before_version=rows[limit - 1]["version_no"] if len(rows) > limit else None,
    )


def version_detail(session, user, identifier, version_id):
    allowed = authorize(session, user, "P1_POLICY_READ")
    policy_for(session, identifier, allowed)
    return dict(version_for(session, identifier, version_id))


def history(session, user, limit, cursor=None):
    allowed = authorize(session, user, "P1_POLICY_READ")
    query = select(policies).where(visible(allowed))
    if cursor:
        at, identifier = repository.decode_cursor(cursor)
        query = query.where(
            or_(
                policies.c.created_at < at,
                and_(policies.c.created_at == at, policies.c.policy_id < identifier),
            )
        )
    rows = list(
        session.execute(
            query.order_by(policies.c.created_at.desc(), policies.c.policy_id.desc()).limit(limit + 1)
        ).mappings()
    )
    return dict(
        items=[policy_view(session, r) for r in rows[:limit]],
        next_cursor=repository.encode_cursor(rows[limit - 1]["created_at"], rows[limit - 1]["policy_id"])
        if len(rows) > limit
        else None,
    )


def comparison_for(session, identifier, allowed):
    row = (
        session.execute(
            select(comparisons)
            .join(policies, comparisons.c.policy_id == policies.c.policy_id)
            .where(comparisons.c.comparison_id == identifier, visible(allowed))
        )
        .mappings()
        .first()
    )
    if row is None:
        raise APIError(404, "POLICY_COMPARISON_NOT_FOUND")
    return row


def comparison_view(session, row):
    candidate = version_for(session, row["policy_id"], row["to_version_id"])
    head = session.scalar(select(policies.c.latest_version).where(policies.c.policy_id == row["policy_id"]))
    return dict(
        row,
        candidate_status=candidate["status"],
        reviewable=row["status"] == "PENDING_REVIEW"
        and candidate["status"] == "PENDING_REVIEW"
        and candidate["version_no"] == head,
        reviews=[
            dict(r)
            for r in session.execute(
                select(reviews).where(reviews.c.comparison_id == row["comparison_id"])
            ).mappings()
        ],
    )


def compare(session, user, identifier, body, key):
    allowed = authorize(session, user, "P1_POLICY_WRITE", lock=True)
    policy_for(session, identifier, allowed)
    after = version_for(session, identifier, str(body.to_version_id))
    before = version_for(session, identifier, str(body.from_version_id)) if body.from_version_id else None
    if (before and before["version_no"] >= after["version_no"]) or (
        before is None and after["version_no"] != 1
    ):
        raise APIError(422, "INVALID_POLICY_VERSION_PAIR")
    fingerprint = digest({"policy_id": identifier, **body.model_dump()})
    previous = replay(session, user, "POLICY_COMPARE", key, fingerprint)
    if previous:
        return previous, True
    diff = PolicyDiff.model_validate(policy_analysis.text_diff(before, after)).model_dump(mode="json")
    impact = normalize(policy_analysis.impact(session, user, team_ids(session, identifier), before))
    impact = PolicyImpact.model_validate(impact).model_dump(mode="json")
    cid = str(uuid4())
    session.execute(
        comparisons.insert().values(
            comparison_id=cid,
            policy_id=identifier,
            from_version_id=before["version_id"] if before else None,
            to_version_id=after["version_id"],
            diff=diff,
            impact=impact,
            analysis_hash=digest({"diff": diff, "impact": impact}),
            created_by=user["user_id"],
        )
    )
    result = comparison_view(session, comparison_for(session, cid, allowed))
    remember(session, user, "POLICY_COMPARE", key, fingerprint, result, response_status=201)
    audit.record(session, user["user_id"], "COMPARE_POLICY", "P1_POLICY", identifier)
    return result, False


def comparison_detail(session, user, identifier):
    allowed = authorize(session, user, "P1_POLICY_READ")
    return comparison_view(session, comparison_for(session, identifier, allowed))


def comparison_history(session, user, identifier, limit, cursor=None):
    allowed = authorize(session, user, "P1_POLICY_READ")
    policy_for(session, identifier, allowed)
    query = select(comparisons).where(comparisons.c.policy_id == identifier)
    if cursor:
        at, cid = repository.decode_cursor(cursor)
        query = query.where(
            or_(
                comparisons.c.created_at < at,
                and_(comparisons.c.created_at == at, comparisons.c.comparison_id < cid),
            )
        )
    rows = list(
        session.execute(
            query.order_by(comparisons.c.created_at.desc(), comparisons.c.comparison_id.desc()).limit(
                limit + 1
            )
        ).mappings()
    )
    return dict(
        items=[comparison_view(session, r) for r in rows[:limit]],
        next_cursor=repository.encode_cursor(rows[limit - 1]["created_at"], rows[limit - 1]["comparison_id"])
        if len(rows) > limit
        else None,
    )


def review(session, user, identifier, body, key):
    allowed = authorize(session, user, "P1_POLICY_REVIEW", lock=True)
    row = comparison_for(session, identifier, allowed)
    policy = policy_for(session, row["policy_id"], allowed, lock=True)
    fingerprint = digest({"comparison_id": identifier, **body.model_dump()})
    previous = replay(session, user, "POLICY_REVIEW", key, fingerprint)
    if previous:
        return previous, True
    candidate = version_for(session, row["policy_id"], row["to_version_id"])
    if candidate["version_no"] != policy["latest_version"]:
        raise APIError(409, "POLICY_CANDIDATE_SUPERSEDED")
    changed = session.execute(
        update(comparisons)
        .where(
            comparisons.c.comparison_id == identifier,
            comparisons.c.status == "PENDING_REVIEW",
            comparisons.c.revision == body.expected_revision,
        )
        .values(status=body.decision, revision=comparisons.c.revision + 1)
    )
    if changed.rowcount != 1:
        raise APIError(409, "POLICY_REVIEW_CONFLICT")
    changed = session.execute(
        update(versions)
        .where(versions.c.version_id == candidate["version_id"], versions.c.status == "PENDING_REVIEW")
        .values(status=body.decision, revision=versions.c.revision + 1)
    )
    if changed.rowcount != 1:
        raise APIError(409, "POLICY_REVIEW_CONFLICT")
    session.execute(
        reviews.insert().values(
            review_id=str(uuid4()),
            comparison_id=identifier,
            version_id=candidate["version_id"],
            reviewed_by=user["user_id"],
            decision=body.decision,
            reason=body.reason,
        )
    )
    result = comparison_view(session, comparison_for(session, identifier, allowed))
    remember(session, user, "POLICY_REVIEW", key, fingerprint, result)
    audit.record(
        session, user["user_id"], "REVIEW_POLICY", "P1_POLICY", row["policy_id"], reason=body.decision
    )
    return result, False
