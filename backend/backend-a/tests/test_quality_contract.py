from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import CheckConstraint, func, inspect, select, text
from sqlalchemy.exc import DBAPIError

from app import finalization, quality_metrics, quality_provenance, quality_service
from app.db import build_engine, session_factory, utcnow
from app.finalization import commit_automatic_reply
from app.model_constraints import user_team_scopes
from app.models import (
    audit_events,
    automation_jobs,
    knowledge_documents,
    messages,
    orders,
    tickets,
)
from app.quality_models import evidence, receipts, reply_records, revisions, rubrics, samples
from app.quality_provenance import sha
from app.quality_schemas import ReplyProvenance
from app.resolution import WorkRejected
from app.seed import seed_minimal, stable_id
from app.staff_models import staff_permissions
from tests.conftest import PASSWORD, ROOT, login_as, migrate
from tests.phase3_helpers import staff_user
from tests.quality_helpers import TEAM, URL, auth, command, confirmed, grant, metrics, review, select_sample


@pytest.mark.postgres
def test_quality_migration_preserves_legacy_and_grants_no_backfill(settings, monkeypatch):
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("PG required")
    migrate(settings, monkeypatch, target="0008")
    e = build_engine(settings)
    f = session_factory(e)
    tid, mid = str(uuid4()), str(uuid4())
    try:
        with f.begin() as s:
            seed_minimal(s, PASSWORD)
            s.execute(
                staff_permissions.insert().values(
                    user_id=stable_id("admin"), permission="VOC_IMPROVEMENT_MANAGE"
                )
            )
            s.execute(
                tickets.insert().values(
                    ticket_id=tid,
                    customer_id=stable_id("customer1/profile"),
                    sla_due_at=utcnow(),
                    team_id=TEAM,
                )
            )
            s.execute(
                messages.insert().values(
                    message_id=mid,
                    ticket_id=tid,
                    cycle_no=1,
                    role="SYSTEM",
                    direction="OUT",
                    visibility="PUBLIC",
                    body="synthetic old final",
                    final_reply=True,
                )
            )
            oldmessages = list(s.execute(select(messages)))
            oldgrants = list(s.execute(select(staff_permissions)))
        cfg = Config(str(ROOT / "alembic.ini"))
        alembic_command.upgrade(cfg, "head")
        with f.begin() as s:
            assert list(s.execute(select(messages))) == oldmessages
            assert list(s.execute(select(staff_permissions))) == oldgrants
            assert s.scalar(select(func.count()).select_from(reply_records)) == 0
            assert s.scalar(text("SELECT version_num FROM alembic_version")) == "0009"
        alembic_command.check(cfg)
        for table in (rubrics, reply_records, evidence, samples, revisions, receipts):
            assert {c.name for c in table.constraints if isinstance(c, CheckConstraint)} == {
                c["name"] for c in inspect(e).get_check_constraints(table.name)
            }
        alembic_command.downgrade(cfg, "0008")
        alembic_command.upgrade(cfg, "head")
        alembic_command.check(cfg)
    finally:
        e.dispose()


@pytest.mark.parametrize("kind", ["SELECT", "REVIEW", "REASSIGN", "VOID"])
def test_command_receipt_failure_rolls_back_state_history_audit(client, app, monkeypatch, kind):
    h, a = auth(client, app)
    r, _ = confirmed(app)
    sid = None
    if kind != "SELECT":
        sid = select_sample(client, h, r["message_id"]).json()["sample_id"]

    def fail(*a, **kw):
        raise RuntimeError("synthetic quality receipt failure")

    monkeypatch.setattr(quality_service, "save_receipt", fail)
    if kind == "SELECT":
        response = select_sample(client, h, r["message_id"])
    elif kind == "REVIEW":
        response = review(client, a, sid)
    else:
        body = {"expected_revision": 1, "change_reason": "OTHER"}
        if kind == "REASSIGN":
            body["assigned_reviewer_id"] = stable_id("admin")
        response = client.post(
            f"{URL}/samples/{sid}/{'assignment' if kind == 'REASSIGN' else 'void'}",
            headers={**h, "Idempotency-Key": "quality-atomic-0001"},
            json=body,
        )
    assert response.status_code == 500
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(samples)) == (0 if kind == "SELECT" else 1)
        assert s.scalar(select(func.count()).select_from(revisions)) == (0 if kind == "SELECT" else 1)
        assert s.scalar(select(func.count()).select_from(receipts)) == (0 if kind == "SELECT" else 1)
        if sid:
            assert s.scalar(select(samples.c.current_revision)) == 1


def test_material_masking_purpose_denial_and_minimal_audit_receipts(client, app, caplog):
    h, a = auth(client, app)
    c = command(app, provenance="question", answer="연락처 010-1234-5678 test.person@example.test")
    with app.state.session_factory.begin() as s:
        tid = s.scalar(select(automation_jobs.c.ticket_id).where(automation_jobs.c.job_id == str(c.job_id)))
        o = (
            s.execute(select(orders).where(orders.c.customer_id == stable_id("customer1/profile")))
            .mappings()
            .first()
        )
        s.execute(
            tickets.update()
            .where(tickets.c.ticket_id == tid)
            .values(order_id=o["order_id"], product_id=o["product_id"])
        )
        s.execute(
            messages.update()
            .where(messages.c.message_id == str(c.provenance.source_message_id))
            .values(body="질문 " + o["order_number"] + " 010-1234-5678 test.person@example.test")
        )
    with app.state.session_factory.begin() as s:
        r = commit_automatic_reply(s, c)
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    denied = client.post(f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "ACTIVE_SUPPORT"})
    assert denied.status_code == 403
    data = client.post(f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "QUALITY_REVIEW"})
    assert data.status_code == 200
    assert all(x not in data.text for x in [o["order_number"], "010-1234-5678", "test.person@example.test"])
    assert all(x not in caplog.text for x in [o["order_number"], "010-1234-5678", "test.person@example.test"])
    with app.state.session_factory() as s:
        assert not any(c in receipts.c for c in ["body", "payload", "response_snapshot"])
        auditrows = list(s.execute(select(audit_events).where(audit_events.c.target_id == sid)).mappings())
        assert any(x["result"] == "DENIED" for x in auditrows)
        assert all(x["payload"] == {} for x in auditrows)


def test_scope_filter_unassigned_reviewer_and_capability_revoked(client, app):
    h, a = auth(client, app)
    r, _ = confirmed(app)
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    staff_user(app, "qa-other-agent")
    grant(app, "qa-other-agent", "QUALITY_REVIEW")
    other = login_as(client, "qa-other-agent")
    assert (
        client.post(
            f"{URL}/samples/{sid}/material", headers=other, json={"purpose_code": "QUALITY_REVIEW"}
        ).status_code
        == 404
    )
    assert metrics(client, h, team_ids=str(uuid4())).status_code == 403
    with app.state.session_factory.begin() as s:
        s.execute(
            staff_permissions.delete().where(
                staff_permissions.c.user_id == stable_id("agent"),
                staff_permissions.c.permission == "QUALITY_REVIEW",
            )
        )
    assert review(client, a, sid).status_code == 403
    assert (
        client.post(
            f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "QUALITY_REVIEW"}
        ).status_code
        == 403
    )


def test_pages_rubric_separation_and_zero_denominator(client, app):
    h, a = auth(client, app)
    d = metrics(client, h).json()["attributed"]
    assert d["accuracy_rate"] is None and d["evaluation_coverage"] is None
    for i in range(3):
        r, _ = confirmed(app)
        sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    first = client.get(URL + "/candidates?origin=SYNTHETIC&limit=1", headers=h).json()
    second = client.get(
        URL + "/candidates",
        headers=h,
        params={"origin": "SYNTHETIC", "limit": 1, "cursor": first["next_cursor"]},
    ).json()
    assert first["items"][0]["message_id"] != second["items"][0]["message_id"]
    assert client.get(URL + "/samples?limit=101", headers=h).status_code == 422
    assert review(client, a, sid).status_code == 201
    with app.state.session_factory.begin() as s:
        rr = dict(s.execute(select(rubrics)).mappings().one())
        rr["version"] = "DEV_QUALITY_V2"
        s.execute(rubrics.insert().values(**rr))
    response = client.post(
        URL + "/samples",
        headers={**h, "Idempotency-Key": "quality-rubric-two"},
        json={
            "message_id": r["message_id"],
            "rubric_version": "DEV_QUALITY_V2",
            "review_team_id": TEAM,
            "assigned_reviewer_id": stable_id("agent"),
        },
    )
    assert response.status_code == 201
    assert metrics(client, h).json()["attributed"]["reviewed_count"] == 1
    assert metrics(client, h, rubric_version="DEV_QUALITY_V2").json()["attributed"]["reviewed_count"] == 0


def test_hash_only_policy_does_not_restore_body_or_match(client, app):
    h, a = auth(client, app)
    c = command(app, provenance="full")
    with app.state.session_factory.begin() as s:
        s.execute(
            knowledge_documents.update()
            .where(knowledge_documents.c.document_id == str(c.provenance.evidence[0].document_id))
            .values(body="changed without a valid original body hash")
        )
    with app.state.session_factory.begin() as s:
        r = commit_automatic_reply(s, c)
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    d = client.post(
        f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "QUALITY_REVIEW"}
    ).json()
    assert d["material_state"] == "INSUFFICIENT_MATERIAL" and d["policies"][0]["body"] is None
    assert d["policies"][0]["material_state"] == "REFERENCES_ONLY"
    assert review(client, a, sid, policy="MATCH").status_code == 409


@pytest.mark.parametrize("expiry", ["lease", "approval"])
def test_fencing_rechecked_after_provenance_validation(app, monkeypatch, expiry):
    c = command(app, provenance="full")
    now = utcnow()
    clock = [now]
    if expiry == "approval":
        with app.state.session_factory.begin() as s:
            from app.models import approvals

            s.execute(
                approvals.update()
                .where(approvals.c.approval_id == str(c.provenance.approval_id))
                .values(expires_at=now + timedelta(seconds=10))
            )
    original = quality_provenance.prepare

    def prepare(*a, **kw):
        result = original(*a, **kw)
        clock[0] = now + timedelta(minutes=20 if expiry == "lease" else 1)
        return result

    monkeypatch.setattr(finalization, "utcnow", lambda: clock[0])
    monkeypatch.setattr(quality_provenance, "prepare", prepare)
    with (
        pytest.raises(WorkRejected, match="INVALID_LEASE" if expiry == "lease" else "PROVENANCE_EXPIRED"),
        app.state.session_factory.begin() as s,
    ):
        commit_automatic_reply(s, c)


def test_current_snapshot_auth_population_review_counts_do_not_mix(client, app, monkeypatch):
    h, a = auth(client, app)
    r, _ = confirmed(app)
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    assert review(client, a, sid).status_code == 201
    original = quality_metrics.aggregate
    switched = False

    def aggregate(session, *args, **kw):
        nonlocal switched
        result = original(session, *args, **kw)
        assert session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        if not switched:
            switched = True
            with app.state.session_factory.begin() as s:
                s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
        return result

    monkeypatch.setattr(quality_metrics, "aggregate", aggregate)
    d = metrics(client, h).json()
    assert d["attributed"]["reviewed_count"] == 1 and d["review_team_sample_counts"]["reviewed_count"] == 1
    assert metrics(client, h).json()["attributed"]["confirmed_response_count"] == 0


def test_half_open_response_period_and_utc_boundary(client, app, monkeypatch):
    h, a = auth(client, app)
    start = utcnow() - timedelta(minutes=2)
    end = start + timedelta(minutes=1)
    for at in (start, end):
        monkeypatch.setattr(finalization, "utcnow", lambda: at)
        confirmed(app)
    response = metrics(client, h, response_start=start.isoformat(), response_end=end.isoformat())
    assert response.status_code == 200, response.text
    assert response.json()["attributed"]["confirmed_response_count"] == 1
    from datetime import timezone

    offset = timezone(timedelta(hours=9))
    assert (
        metrics(
            client,
            h,
            response_start=start.astimezone(offset).isoformat(),
            response_end=end.astimezone(offset).isoformat(),
        ).json()["attributed"]
        == response.json()["attributed"]
    )


def test_quality_retention_references_and_deferred_evidence_seal(client, app, monkeypatch):
    from app import retention

    h, a = auth(client, app)
    r, c = confirmed(app, provenance="full")
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    assert review(client, a, sid, policy="MATCH").status_code == 201
    grant(app, "admin", "RETENTION_GLOBAL_REVIEW")
    grant(app, "admin", "VOC_IMPROVEMENT_MANAGE")
    from tests.test_voc_improvements import create as create_voc

    create_voc(client, h)
    now = utcnow() + timedelta(days=200)
    original = retention.build_report

    def synthetic_snapshot(session, user, body):
        session.info["snapshot_as_of"] = now
        return original(session, user, body)

    monkeypatch.setattr(retention, "build_report", synthetic_snapshot)
    response = client.post(
        "/api/v1/staff/retention/dry-run",
        headers=h,
        json={"purpose_code": "RETENTION_REVIEW", "scope": "GLOBAL", "as_of": now.isoformat()},
    )
    assert response.status_code == 200, response.text
    targets = {t["target"]: t for t in response.json()["targets"]}
    assert targets["messages"]["reason_counts"]["QUALITY_CONFIRMED_REPLY_REFERENCE"] >= 2
    assert targets["automatic_reply_records"]["blocked_count"] == 1
    assert targets["quality_review_revisions"]["candidate_count"] == 0
    assert "VOC_RETENTION_POLICY_NOT_DEFINED" in targets["voc_improvement_profiles"]["reason_counts"]
    if app.state.engine.dialect.name == "postgresql":
        with (
            pytest.raises(DBAPIError, match="QUALITY_EVIDENCE_SEALED"),
            app.state.session_factory.begin() as s,
        ):
            er = dict(s.execute(select(evidence)).mappings().one())
            er["ordinal"] = 2
            s.execute(evidence.insert().values(**er))
        with pytest.raises(DBAPIError), app.state.session_factory.begin() as s:
            s.execute(reply_records.update().values(model_version="overwrite"))
        with pytest.raises(RuntimeError, match="retain 0009"):
            alembic_command.downgrade(Config(str(ROOT / "alembic.ini")), "0008")


def test_long_verified_policy_is_explicitly_incomplete_for_judgment(client, app):
    h, a = auth(client, app)
    c = command(app, provenance="full")
    p = c.provenance.model_dump(mode="json")
    policy = "합성 긴 정책 내용 " * 2000
    p["evidence"][0]["content_hash"] = sha(policy)
    with app.state.session_factory.begin() as s:
        s.execute(
            knowledge_documents.update()
            .where(knowledge_documents.c.document_id == p["evidence"][0]["document_id"])
            .values(body=policy, content_hash=sha(policy))
        )
        from app.models import ai_suggestions

        s.execute(
            ai_suggestions.update()
            .where(ai_suggestions.c.suggestion_id == p["suggestion_id"])
            .values(evidence_refs=p["evidence"])
        )
    c = c.model_copy(update={"provenance": ReplyProvenance.model_validate(p)})
    with app.state.session_factory.begin() as s:
        r = commit_automatic_reply(s, c)
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    d = client.post(
        f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "QUALITY_REVIEW"}
    ).json()
    assert d["material_state"] == "INSUFFICIENT_MATERIAL" and d["truncated_fields"] == ["POLICY"]
    assert d["policies"][0]["truncated"] and len(d["policies"][0]["body"]) == 10000
    assert review(client, a, sid, policy="MATCH").status_code == 409
