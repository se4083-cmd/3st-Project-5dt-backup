"""Narrow QA boundary: no changes to ticket_scope or customer360."""

import re
from uuid import uuid4

from sqlalchemy import and_, exists, false, or_, select

from app import audit, followups
from app import repository as repo
from app.analytics_canonical import digest
from app.automation_control import capability
from app.db import utcnow
from app.errors import APIError, denied
from app.models import knowledge_documents, messages, orders, tickets, users
from app.quality_metrics import allowed_teams
from app.quality_models import evidence, receipts, reply_records, revisions, rubrics, samples
from app.quality_provenance import sha
from app.quality_schemas import Candidate, SampleView
from app.staff_models import staff_permissions


def grants(session, user):
    if user["role"] not in {"ADMIN", "AGENT"}:
        raise APIError(403, "STAFF_ROLE_REQUIRED", user["user_id"])
    return set(
        session.scalars(
            select(staff_permissions.c.permission).where(staff_permissions.c.user_id == user["user_id"])
        )
    )


def actor(session, user):
    fresh = (
        session.execute(
            select(users).where(users.c.user_id == user["user_id"]).with_for_update(key_share=True)
        )
        .mappings()
        .one()
    )
    if not fresh["active"]:
        raise APIError(401, "INVALID_CREDENTIALS", user["user_id"])
    return fresh


def scope(session, user, *, management=False):
    g = grants(session, user)
    management_scope = (
        and_(
            followups.team_scope(user, samples.c.review_team_id),
            or_(reply_records.c.attribution_team_id.is_not(None), "QUALITY_UNATTRIBUTED_MANAGE" in g),
        )
        if user["role"] == "ADMIN" and "QUALITY_SAMPLE_MANAGE" in g
        else false()
    )
    review_scope = (
        and_(
            samples.c.assigned_reviewer_id == user["user_id"],
            followups.team_scope(user, samples.c.review_team_id),
        )
        if "QUALITY_REVIEW" in g
        else false()
    )
    return management_scope if management else or_(management_scope, review_scope)


def get_sample(session, user, sample_id, *, write=False, review=False):
    if review:
        capability(session, user, "QUALITY_REVIEW")
        allowed = and_(
            samples.c.assigned_reviewer_id == user["user_id"],
            followups.team_scope(user, samples.c.review_team_id),
        )
    else:
        allowed = scope(session, user, management=write)
    query = select(samples).join(reply_records).where(samples.c.sample_id == sample_id, allowed)
    if write:
        query = query.with_for_update(of=samples)
    s = session.execute(query).mappings().first()
    if not s:
        raise denied(user["user_id"], "QUALITY_SAMPLE", sample_id)
    return s


def reviewer(session, reviewer_id, team_id):
    u = repo.get_user(session, reviewer_id)
    if (
        not u
        or not u["active"]
        or u["role"] not in {"ADMIN", "AGENT"}
        or not session.scalar(
            select(
                exists().where(
                    staff_permissions.c.user_id == reviewer_id,
                    staff_permissions.c.permission == "QUALITY_REVIEW",
                )
            )
        )
        or not session.scalar(
            select(exists().where(users.c.user_id == reviewer_id, followups.team_scope(u, team_id)))
        )
    ):
        raise APIError(409, "QUALITY_REVIEWER_UNAVAILABLE")


def candidate_list(session, user, limit, cursor, *, origin, unattributed=False):
    capability(session, user, "QUALITY_SAMPLE_MANAGE", admin=True)
    if unattributed:
        capability(session, user, "QUALITY_UNATTRIBUTED_MANAGE", admin=True)
        if not allowed_teams(session, user):
            raise APIError(403, "QUALITY_TEAM_SCOPE_DENIED", user["user_id"])
        allowed = reply_records.c.attribution_team_id.is_(None)
    else:
        allowed = followups.team_scope(user, reply_records.c.attribution_team_id)
    rows, next_cursor = repo.page_rows(
        session,
        reply_records,
        and_(allowed, reply_records.c.origin == origin),
        reply_records.c.committed_at,
        reply_records.c.message_id,
        limit,
        cursor,
    )
    audit.record(session, user["user_id"], "QUALITY_CANDIDATE_LIST", "QUALITY_SAMPLE", None)
    return {
        "items": [Candidate.model_validate({k: r[k] for k in Candidate.model_fields}) for r in rows],
        "next_cursor": next_cursor,
    }


def sample_list(session, user, limit, cursor):
    g = grants(session, user)
    if not ({"QUALITY_REVIEW", "QUALITY_SAMPLE_MANAGE"} & g):
        raise APIError(403, "EXPLICIT_PERMISSION_REQUIRED", user["user_id"])
    allowed = exists(
        select(1).where(reply_records.c.message_id == samples.c.message_id, scope(session, user))
    ).correlate(samples)
    rows, next_cursor = repo.page_rows(
        session, samples, allowed, samples.c.selected_at, samples.c.sample_id, limit, cursor
    )
    audit.record(session, user["user_id"], "QUALITY_SAMPLE_LIST", "QUALITY_SAMPLE", None)
    return {
        "items": [SampleView.model_validate({k: r[k] for k in SampleView.model_fields}) for r in rows],
        "next_cursor": next_cursor,
    }


def old_receipt(session, user, key, operation, body, sample_id=None):
    hashed = digest({"operation": operation, "sample_id": sample_id, "body": body.model_dump(mode="json")})
    old = repo.row(session, receipts, receipts.c.user_id == user["user_id"], receipts.c.key == key)
    if old:
        get_sample(session, user, old["sample_id"], write=operation != "REVIEW", review=operation == "REVIEW")
        if old["operation"] != operation or old["request_hash"] != hashed:
            raise APIError(409, "IDEMPOTENCY_CONFLICT")
        return hashed, {"sample_id": old["sample_id"], "revision": old["revision"]}
    return hashed, None


def save_receipt(session, user, key, operation, hashed, sample_id, revision):
    session.execute(
        receipts.insert().values(
            user_id=user["user_id"],
            key=key,
            operation=operation,
            request_hash=hashed,
            sample_id=sample_id,
            revision=revision,
            created_at=utcnow(),
        )
    )


def event(
    session,
    user,
    sample,
    revision,
    kind,
    change_reason,
    *,
    accuracy=None,
    policy_alignment=None,
    reason_codes=None,
    independent="UNKNOWN",
):
    session.execute(
        revisions.insert().values(
            sample_id=sample["sample_id"],
            revision=revision,
            event_kind=kind,
            actor_id=user["user_id"],
            assigned_reviewer_id=sample["assigned_reviewer_id"],
            accuracy=accuracy,
            policy_alignment=policy_alignment,
            reason_codes=reason_codes or [],
            change_reason=change_reason,
            independent_review=independent,
            recorded_at=utcnow(),
        )
    )
    audit.record(session, user["user_id"], "QUALITY_" + kind, "QUALITY_SAMPLE", sample["sample_id"])


def create_sample(session, user, body, key):
    user = actor(session, user)
    capability(session, user, "QUALITY_SAMPLE_MANAGE", admin=True)
    hashed, old = old_receipt(session, user, key, "SELECT", body)
    if old:
        return old, True
    with session.begin_nested():
        r = (
            session.execute(
                select(reply_records)
                .where(reply_records.c.message_id == str(body.message_id))
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not r:
            raise denied(user["user_id"], "QUALITY_REPLY", str(body.message_id))
        if r["attribution_team_id"] is None:
            if "QUALITY_UNATTRIBUTED_MANAGE" not in grants(session, user):
                raise denied(user["user_id"], "QUALITY_REPLY", str(body.message_id))
        else:
            followups.check_team(session, user, r["attribution_team_id"])
            if r["attribution_team_id"] != str(body.review_team_id):
                raise APIError(409, "QUALITY_REVIEW_TEAM_MISMATCH")
        followups.check_team(session, user, str(body.review_team_id))
        reviewer(session, str(body.assigned_reviewer_id), str(body.review_team_id))
        if not repo.row(session, rubrics, rubrics.c.version == body.rubric_version):
            raise APIError(422, "QUALITY_RUBRIC_UNKNOWN")
        if repo.row(
            session,
            samples,
            samples.c.message_id == str(body.message_id),
            samples.c.rubric_version == body.rubric_version,
        ):
            raise APIError(409, "QUALITY_SAMPLE_ALREADY_EXISTS")
        m = repo.row(session, messages, messages.c.message_id == r["message_id"])
        if not valid_reply(m, r):
            raise APIError(409, "QUALITY_MATERIAL_CHANGED")
        s = dict(
            sample_id=str(uuid4()),
            message_id=r["message_id"],
            rubric_version=body.rubric_version,
            review_team_id=str(body.review_team_id),
            assigned_reviewer_id=str(body.assigned_reviewer_id),
            status="OPEN",
            current_revision=1,
            created_by=user["user_id"],
            selected_at=utcnow(),
        )
        session.execute(samples.insert().values(**s))
        event(session, user, s, 1, "SELECT", "MANUAL_SELECTION")
        save_receipt(session, user, key, "SELECT", hashed, s["sample_id"], 1)
    return {"sample_id": s["sample_id"], "revision": 1}, False


def valid_reply(m, r):
    return bool(
        m
        and m["ticket_id"] == r["ticket_id"]
        and m["cycle_no"] == r["cycle_no"]
        and m["direction"] == "OUT"
        and m["visibility"] == "PUBLIC"
        and m["final_reply"]
        and m["role"] == "SYSTEM"
        and sha(m["body"]) == r["reply_sha256"]
    )


def mask(text, order_number=None):
    if text is None:
        return None
    if order_number:
        text = text.replace(order_number, "[ORDER]")
    for rx in (
        r"(?i)(?:주문번호|order[_ -]?(?:number|no))\s*[:#=-]?\s*[A-Za-z0-9_-]+",
        r"https?://\S+",
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b",
        r"(?:\+?82[- .]?)?0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}",
        r"\b\d{5,}\b",
        r"[가-힣]{2,4}\s*(?:고객님|님)",
    ):
        text = re.sub(rx, "[MASKED]", text)
    return text[:10000]


def load_material(session, s):
    r = repo.row(session, reply_records, reply_records.c.message_id == s["message_id"])
    m = repo.row(session, messages, messages.c.message_id == r["message_id"])
    good = valid_reply(m, r)
    q = (
        repo.row(session, messages, messages.c.message_id == r["source_message_id"])
        if r["source_message_id"]
        else None
    )
    question_ok = bool(
        q
        and q["ticket_id"] == r["ticket_id"]
        and q["cycle_no"] == r["cycle_no"]
        and q["direction"] == "IN"
        and q["visibility"] == "PUBLIC"
        and sha(q["body"]) == r["question_sha256"]
    )
    order_number = session.scalar(
        select(orders.c.order_number)
        .join(tickets, tickets.c.order_id == orders.c.order_id)
        .where(tickets.c.ticket_id == r["ticket_id"])
    )
    policies = []
    truncated = []
    if good and len(m["body"]) > 10000:
        truncated.append("REPLY")
    if question_ok and len(q["body"]) > 10000:
        truncated.append("QUESTION")
    for e in session.execute(
        select(evidence).where(evidence.c.message_id == r["message_id"]).order_by(evidence.c.ordinal)
    ).mappings():
        d = repo.row(session, knowledge_documents, knowledge_documents.c.document_id == e["document_id"])
        match = bool(d and d["version"] == e["document_version"] and d["content_hash"] == e["content_hash"])
        verified = match and bool(e["body_sha256"]) and sha(d["body"]) == e["body_sha256"]
        policies.append(
            dict(
                document_id=e["document_id"],
                version=e["document_version"],
                content_hash=e["content_hash"],
                chunk_ref=e["chunk_ref"],
                material_state="VERIFIED_BODY"
                if verified
                else "REFERENCES_ONLY"
                if match and e["body_sha256"] is None
                else "MATERIAL_CHANGED",
                body=mask(d["body"], order_number) if verified else None,
                truncated=bool(verified and len(d["body"]) > 10000),
            )
        )
    if any(p["truncated"] for p in policies):
        truncated.append("POLICY")
    criterion = repo.row(session, rubrics, rubrics.c.version == s["rubric_version"])
    state = (
        "MATERIAL_CHANGED"
        if not good
        or (q and not question_ok)
        or any(p["material_state"] == "MATERIAL_CHANGED" for p in policies)
        else "RECORDED_MATERIAL"
        if question_ok and policies and all(p["body"] is not None for p in policies) and not truncated
        else "INSUFFICIENT_MATERIAL"
    )
    return dict(
        sample_id=s["sample_id"],
        message_id=r["message_id"],
        cycle_no=r["cycle_no"],
        origin=r["origin"],
        provenance_state=r["provenance_state"],
        material_state=state,
        reply=mask(m["body"], order_number) if good else None,
        question=mask(q["body"], order_number) if question_ok else None,
        policies=policies,
        model_version=r["model_version"],
        prompt_version=r["prompt_version"],
        rubric_version=s["rubric_version"],
        rubric_criteria=criterion["criteria"],
        as_of=session.info.get("snapshot_as_of", utcnow()),
        truncated_fields=truncated,
    )


def material(session, user, sample_id, purpose):
    if purpose != "QUALITY_REVIEW":
        raise APIError(403, "QUALITY_PURPOSE_REQUIRED", user["user_id"], "QUALITY_SAMPLE", sample_id)
    s = get_sample(session, user, sample_id, review=True)
    if s["status"] == "VOID":
        raise APIError(403, "QUALITY_SAMPLE_VOID", user["user_id"], "QUALITY_SAMPLE", sample_id)
    result = load_material(session, s)
    audit.record(
        session,
        user["user_id"],
        "QUALITY_MATERIAL_READ",
        "QUALITY_SAMPLE",
        sample_id,
        reason="QUALITY_REVIEW",
    )
    return result


def mutate(session, user, sample_id, body, key, operation):
    user = actor(session, user)
    capability(
        session,
        user,
        "QUALITY_REVIEW" if operation == "REVIEW" else "QUALITY_SAMPLE_MANAGE",
        admin=operation != "REVIEW",
    )
    hashed, old = old_receipt(session, user, key, operation, body, sample_id)
    if old:
        return old, True
    with session.begin_nested():
        s = dict(get_sample(session, user, sample_id, write=True, review=operation == "REVIEW"))
        if s["current_revision"] != body.expected_revision:
            raise APIError(409, "QUALITY_REVISION_CONFLICT")
        if s["status"] == "VOID":
            raise APIError(409, "QUALITY_SAMPLE_VOID")
        rev = s["current_revision"] + 1
        kwargs = {}
        changes = {"current_revision": rev}
        if operation == "REVIEW":
            mat = load_material(session, s)
            if mat["reply"] is None:
                raise APIError(409, "QUALITY_MATERIAL_CHANGED")
            if body.accuracy != "UNDETERMINABLE" and (
                mat["question"] is None or set(mat["truncated_fields"]) & {"REPLY", "QUESTION"}
            ):
                raise APIError(409, "QUALITY_QUESTION_MATERIAL_REQUIRED")
            if body.policy_alignment in {"MATCH", "MISMATCH"} and (
                not mat["policies"]
                or not all(
                    p["material_state"] == "VERIFIED_BODY" and not p["truncated"] for p in mat["policies"]
                )
            ):
                raise APIError(409, "QUALITY_POLICY_MATERIAL_REQUIRED")
            previous = session.scalar(
                select(exists().where(revisions.c.sample_id == sample_id, revisions.c.event_kind == "REVIEW"))
            )
            if previous == (body.change_reason == "INITIAL_REVIEW"):
                raise APIError(409, "QUALITY_REVIEW_CHANGE_REASON_REQUIRED")
            r = repo.row(session, reply_records, reply_records.c.message_id == s["message_id"])
            approver = r["approval_reviewer_id"]
            kwargs = dict(
                accuracy=body.accuracy,
                policy_alignment=body.policy_alignment,
                reason_codes=sorted(set(body.reason_codes)),
                independent="UNKNOWN" if not approver else "NO" if approver == user["user_id"] else "YES",
            )
        elif operation == "REASSIGN":
            reviewer(session, str(body.assigned_reviewer_id), s["review_team_id"])
            changes["assigned_reviewer_id"] = str(body.assigned_reviewer_id)
            s["assigned_reviewer_id"] = str(body.assigned_reviewer_id)
        else:
            changes["status"] = "VOID"
        event(session, user, s, rev, operation, body.change_reason, **kwargs)
        session.execute(samples.update().where(samples.c.sample_id == sample_id).values(**changes))
        save_receipt(session, user, key, operation, hashed, sample_id, rev)
    return {"sample_id": sample_id, "revision": rev}, False


def history(session, user, sample_id, limit, before):
    get_sample(session, user, sample_id)
    q = select(revisions).where(revisions.c.sample_id == sample_id)
    if before:
        q = q.where(revisions.c.revision < before)
    rows = list(session.execute(q.order_by(revisions.c.revision.desc()).limit(limit + 1)).mappings())
    audit.record(session, user["user_id"], "QUALITY_HISTORY_READ", "QUALITY_SAMPLE", sample_id)
    return {
        "items": [{k: v for k, v in r.items() if k != "sample_id"} for r in rows[:limit]],
        "next_before_revision": rows[limit - 1]["revision"] if len(rows) > limit else None,
    }
