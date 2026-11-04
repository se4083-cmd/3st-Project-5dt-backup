"""Synthetic QA fixture only; no AI calls, Worker engine or actual account grants."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.db import utcnow
from app.finalization import AutomaticReply, commit_automatic_reply
from app.models import (
    ai_suggestions,
    approvals,
    automation_jobs,
    automation_rules,
    knowledge_documents,
    messages,
    tickets,
)
from app.quality_provenance import sha
from app.seed import stable_id
from app.staff_models import staff_permissions
from tests.conftest import login_as

TEAM = stable_id("team")
URL = "/api/v1/staff/quality"


def grant(app, user, *permissions):
    with app.state.session_factory.begin() as s:
        for p in permissions:
            if not s.scalar(
                select(staff_permissions.c.user_id).where(
                    staff_permissions.c.user_id == stable_id(user), staff_permissions.c.permission == p
                )
            ):
                s.execute(staff_permissions.insert().values(user_id=stable_id(user), permission=p))


def auth(client, app):
    grant(app, "admin", "QUALITY_SAMPLE_MANAGE", "QUALITY_REVIEW", "QUALITY_METRICS_READ")
    grant(app, "agent", "QUALITY_REVIEW")
    return login_as(client, "admin"), login_as(client, "agent")


def command(app, *, team=TEAM, origin="SYNTHETIC", provenance="question", answer="합성 상담 최종 답변"):
    tid, jid, qid = str(uuid4()), str(uuid4()), str(uuid4())
    token = str(uuid4())
    now = utcnow()
    with app.state.session_factory.begin() as s:
        s.execute(
            tickets.insert().values(
                ticket_id=tid,
                customer_id=stable_id("customer1/profile"),
                team_id=team,
                category="DELIVERY",
                sla_due_at=now + timedelta(days=1),
                data_origin=origin,
            )
        )
        s.execute(
            messages.insert().values(
                message_id=qid,
                ticket_id=tid,
                cycle_no=1,
                role="CUSTOMER",
                direction="IN",
                visibility="PUBLIC",
                body="합성 질문",
                created_at=now - timedelta(days=1),
                data_origin=origin,
            )
        )
        s.execute(
            automation_jobs.insert().values(
                job_id=jid,
                ticket_id=tid,
                cycle_no=1,
                expected_ticket_version=1,
                status="RUNNING",
                lease_owner="qa-fixture-worker",
                lease_token=token,
                lease_until=now + timedelta(minutes=10),
            )
        )
        p = None if provenance is None else {"source_message_id": qid}
        if provenance == "full":
            did, rid, sid, aid = [str(uuid4()) for _ in range(4)]
            body = "개발용 합성 정책: 배송 상태를 확인하고 안내합니다."
            dh = sha(body)
            s.execute(
                knowledge_documents.insert().values(
                    document_id=did,
                    policy_key="QA_TEST",
                    title="Synthetic QA policy",
                    version=1,
                    source="LOCAL_SYNTHETIC",
                    blob_path="not-read",
                    content_hash=dh,
                    allowed_topics=["DELIVERY"],
                    active=True,
                    effective_from=now - timedelta(days=2),
                    body=body,
                    approval_status="APPROVED",
                    data_origin=origin,
                )
            )
            s.execute(
                automation_rules.insert().values(
                    rule_id=rid,
                    rule_key="QA_" + rid,
                    version=1,
                    category="DELIVERY",
                    risk_level="LOW",
                    requires_approval=False,
                    conditions={},
                    active=True,
                )
            )
            evidence = [{"document_id": did, "version": 1, "content_hash": dh, "chunk_ref": "chunk-1"}]
            s.execute(
                ai_suggestions.insert().values(
                    suggestion_id=sid,
                    ticket_id=tid,
                    cycle_no=1,
                    revision=1,
                    category="DELIVERY",
                    draft=answer,
                    evidence_refs=evidence,
                    rule_id=rid,
                    rule_version=1,
                    template_key="QA_TEST",
                    prompt_version="prompt-1",
                    model_version="model-1",
                    content_hash=sha(answer),
                    data_origin=origin,
                    created_at=now - timedelta(hours=1),
                )
            )
            s.execute(
                approvals.insert().values(
                    approval_id=aid,
                    ticket_id=tid,
                    suggestion_id=sid,
                    cycle_no=1,
                    ticket_version=1,
                    mode="SYSTEM",
                    decision="APPROVED",
                    gate_snapshot={},
                    content_hash=sha(answer),
                    reviewed_at=now - timedelta(hours=1),
                    expires_at=now + timedelta(days=1),
                    data_origin=origin,
                )
            )
            p.update(
                suggestion_id=sid,
                suggestion_revision=1,
                suggestion_content_hash=sha(answer),
                approval_id=aid,
                model_version="model-1",
                prompt_version="prompt-1",
                retrieval_ref="index-test-1",
                evidence=evidence,
            )
    return AutomaticReply(
        job_id=jid,
        lease_token=token,
        worker_id="qa-fixture-worker",
        cycle_no=1,
        expected_revision=1,
        message=answer,
        provenance=p,
    )


def confirmed(app, **kwargs):
    c = command(app, **kwargs)
    with app.state.session_factory.begin() as s:
        r = commit_automatic_reply(s, c)
    return r, c


def select_sample(client, h, message_id, *, reviewer="agent", team=TEAM, key=None):
    return client.post(
        URL + "/samples",
        headers={**h, "Idempotency-Key": key or "select-" + message_id},
        json={"message_id": message_id, "review_team_id": team, "assigned_reviewer_id": stable_id(reviewer)},
    )


def review(
    client,
    h,
    sid,
    *,
    rev=1,
    accuracy="CORRECT",
    policy="NOT_APPLICABLE",
    key="quality-review-0001",
    reason="INITIAL_REVIEW",
):
    return client.post(
        f"{URL}/samples/{sid}/reviews",
        headers={**h, "Idempotency-Key": key},
        json={
            "expected_revision": rev,
            "accuracy": accuracy,
            "policy_alignment": policy,
            "reason_codes": ["VERIFIED_AGAINST_MATERIAL"],
            "change_reason": reason,
        },
    )


def metrics(client, h, **kwargs):
    p = {
        "response_start": (utcnow() - timedelta(days=1)).isoformat(),
        "response_end": (utcnow() + timedelta(days=1)).isoformat(),
        "origin": "SYNTHETIC",
        **kwargs,
    }
    return client.get(URL + "/metrics", headers=h, params=p)
