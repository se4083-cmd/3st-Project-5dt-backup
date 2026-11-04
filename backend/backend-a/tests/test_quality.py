from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app import quality_provenance
from app.db import utcnow
from app.finalization import commit_automatic_reply
from app.model_constraints import user_team_scopes
from app.models import approvals, automation_jobs, knowledge_documents, messages, tickets
from app.quality_models import reply_records, revisions
from app.quality_schemas import ReplyProvenance
from app.resolution import WorkRejected
from app.seed import stable_id
from tests.conftest import login_as
from tests.quality_helpers import URL, auth, command, confirmed, grant, metrics, review, select_sample


def test_compatible_writer_records_actual_final_and_missing(app):
    r, c = confirmed(app, provenance=None)
    assert set(r) == {"message_id", "ticket_id", "cycle_no", "revision"}
    with app.state.session_factory() as s:
        q = s.execute(select(reply_records)).mappings().one()
        assert q["message_id"] == r["message_id"] and q["job_id"] == str(c.job_id)
        assert q["input_ticket_revision"] == 1 and q["result_ticket_revision"] == 2
        assert q["provenance_state"] == "MISSING" and q["origin"] == "SYNTHETIC"


@pytest.mark.parametrize(
    "bad", ["question", "suggestion", "revision", "approval", "policy_version", "policy_hash", "model"]
)
def test_explicit_mismatched_references_reject_without_final(app, bad):
    c = command(app, provenance="full")
    p = c.provenance.model_dump(mode="json")
    if bad == "question":
        p["source_message_id"] = str(uuid4())
    if bad == "suggestion":
        p["suggestion_id"] = str(uuid4())
    if bad == "revision":
        p["suggestion_revision"] = 99
    if bad == "approval":
        with app.state.session_factory.begin() as s:
            s.execute(
                approvals.update()
                .where(approvals.c.approval_id == p["approval_id"])
                .values(ticket_version=99)
            )
    if bad == "policy_version":
        p["evidence"][0]["version"] = 99
    if bad == "policy_hash":
        p["evidence"][0]["content_hash"] = "0" * 64
    if bad == "model":
        p["model_version"] = "other-model"
    c = c.model_copy(update={"provenance": ReplyProvenance.model_validate(p)})
    with pytest.raises(WorkRejected), app.state.session_factory.begin() as s:
        commit_automatic_reply(s, c)
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(reply_records)) == 0
        assert s.scalar(select(func.count()).select_from(messages).where(messages.c.final_reply)) == 0


def test_full_record_source_material_and_no_generic_ticket_access(client, app):
    h, a = auth(client, app)
    r, c = confirmed(app, provenance="full")
    selected = select_sample(client, h, r["message_id"])
    assert selected.status_code == 201, selected.text
    sid = selected.json()["sample_id"]
    material = client.post(
        f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "QUALITY_REVIEW"}
    )
    assert material.status_code == 200, material.text
    d = material.json()
    assert d["provenance_state"] == "COMPLETE" and d["material_state"] == "RECORDED_MATERIAL"
    assert d["policies"][0]["material_state"] == "VERIFIED_BODY"
    assert "no-store" in material.headers["Cache-Control"]
    assert not any(x in d for x in ("customer_id", "order_id", "profile", "gate_results", "raw_prompt"))
    assert client.get(f"/api/v1/tickets/{r['ticket_id']}", headers=a).status_code == 404
    assert (
        client.post(
            f"/api/v1/staff/tickets/{r['ticket_id']}/internal",
            headers=a,
            json={"purpose_code": "ACTIVE_SUPPORT"},
        ).status_code
        == 404
    )
    assert review(client, a, sid, policy="MATCH").status_code == 201


@pytest.mark.parametrize("user", ["customer1", "agent", "admin"])
def test_roles_without_capability_block(client, app, user):
    h = login_as(client, user)
    assert client.get(URL + "/candidates", headers=h).status_code == 403
    assert client.get(URL + "/samples", headers=h).status_code == 403
    assert metrics(client, h).status_code == 403


def test_sample_idempotency_scope_and_reviewer_revocation(client, app):
    h, a = auth(client, app)
    r, _ = confirmed(app)
    first = select_sample(client, h, r["message_id"], key="quality-select-repeat")
    assert first.status_code == 201, first.text
    assert select_sample(client, h, r["message_id"], key="quality-select-repeat").json() == first.json()
    assert select_sample(client, h, r["message_id"], key="quality-select-other").status_code == 409
    assert (
        select_sample(client, h, r["message_id"], reviewer="admin", key="quality-select-repeat").status_code
        == 409
    )
    sid = first.json()["sample_id"]
    assert (
        client.post(
            f"{URL}/samples/{sid}/material", headers=h, json={"purpose_code": "QUALITY_REVIEW"}
        ).status_code
        == 404
    )
    before = review(client, a, sid)
    assert before.status_code == 201, before.text
    assert review(client, a, sid).json() == before.json()
    assert review(client, a, sid, accuracy="INCORRECT").status_code == 409
    assert review(client, a, sid, key="quality-stale-review").status_code == 409
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("agent")))
    assert review(client, a, sid).status_code == 404
    assert (
        client.post(
            f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "QUALITY_REVIEW"}
        ).status_code
        == 404
    )
    assert client.get(URL + "/samples", headers=a).json()["items"] == []


def test_reassign_preserves_last_review_void_excludes_and_history_append_only(client, app):
    h, a = auth(client, app)
    r, _ = confirmed(app)
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    assert review(client, a, sid).status_code == 201
    re = client.post(
        f"{URL}/samples/{sid}/assignment",
        headers={**h, "Idempotency-Key": "quality-reassign-0001"},
        json={
            "expected_revision": 2,
            "assigned_reviewer_id": stable_id("admin"),
            "change_reason": "REVIEWER_CHANGED",
        },
    )
    assert re.status_code == 201, re.text
    d = metrics(client, h).json()["attributed"]
    assert d["reviewed_count"] == 1 and d["correct"] == 1 and d["evaluation_coverage"] == 1
    assert review(client, a, sid).status_code == 404
    assert review(client, h, sid, rev=3, accuracy="INCORRECT", reason="CORRECTION").status_code == 201
    v = client.post(
        f"{URL}/samples/{sid}/void",
        headers={**h, "Idempotency-Key": "quality-void-0001"},
        json={"expected_revision": 4, "change_reason": "WRONG_TARGET"},
    )
    assert v.status_code == 201, v.text
    d = metrics(client, h).json()["attributed"]
    assert d["void_count"] == 1 and d["reviewed_count"] == 0 and d["accuracy_rate"] is None
    history = client.get(f"{URL}/samples/{sid}/history?limit=2", headers=h).json()
    assert len(history["items"]) == 2 and history["next_before_revision"] == 4
    if app.state.engine.dialect.name == "postgresql":
        with pytest.raises(DBAPIError), app.state.session_factory.begin() as s:
            s.execute(revisions.delete())


def test_unattributed_responsibility_is_not_processing_credit_and_legacy_separate(client, app):
    h, a = auth(client, app)
    r, _ = confirmed(app, team=None)
    assert client.get(URL + "/candidates?unattributed=true&origin=SYNTHETIC", headers=h).status_code == 403
    assert select_sample(client, h, r["message_id"]).status_code == 404
    grant(app, "admin", "QUALITY_UNATTRIBUTED_MANAGE")
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    assert review(client, a, sid).status_code == 201
    with app.state.session_factory.begin() as s:
        assert s.scalar(select(tickets.c.team_id).where(tickets.c.ticket_id == r["ticket_id"])) is None
        # A different old final row has no prospective writer evidence: AUTO remains unknown.
        s.execute(
            messages.insert().values(
                message_id=str(uuid4()),
                ticket_id=r["ticket_id"],
                cycle_no=2,
                role="SYSTEM",
                direction="OUT",
                visibility="PUBLIC",
                body="LEGACY_SYNTHETIC",
                final_reply=True,
                data_origin="SYNTHETIC",
            )
        )
    d = metrics(client, h, include_unattributed="true").json()
    assert d["attributed"]["confirmed_response_count"] == 0
    assert d["unattributed_confirmed_response_count"] == 1 and d["legacy_auto_unknown_count"] == 1
    assert d["review_team_sample_counts"]["reviewed_count"] == 1
    assert d["review_team_evaluation"]["accuracy_rate"] == 1
    assert "coverage" not in d["review_team_evaluation"]
    assert d["attributed"]["accuracy_rate"] is None


def test_hundred_response_denominator_and_origin_and_period(client, app):
    h, a = auth(client, app)
    for i in range(100):
        r, _ = confirmed(app)
        if i < 20:
            sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
            status = "CORRECT" if i < 15 else "INCORRECT" if i < 18 else "UNDETERMINABLE"
            resp = review(client, a, sid, accuracy=status, key=f"quality-hundred-{i}")
            assert resp.status_code == 201, resp.text
    d = metrics(client, h).json()["attributed"]
    assert d["confirmed_response_count"] == 100 and d["reviewed_count"] == 20
    assert d["correct"] == 15 and d["incorrect"] == 3 and d["accuracy_undeterminable"] == 2
    assert d["accuracy_rate"] == 15 / 18 and d["evaluation_coverage"] == 0.2
    assert d["unreviewed_response_count"] == 80 and d["policy_not_applicable"] == 20
    assert d["policy_alignment_rate"] is None
    assert metrics(client, h, origin="APPLICATION").json()["attributed"]["confirmed_response_count"] == 0
    assert metrics(client, h, as_of=utcnow().isoformat()).status_code == 422


def test_missing_material_is_explicit_and_does_not_become_correct(client, app):
    h, a = auth(client, app)
    r, _ = confirmed(app, provenance=None)
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    d = client.post(
        f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "QUALITY_REVIEW"}
    ).json()
    assert d["question"] is None and d["material_state"] == "INSUFFICIENT_MATERIAL"
    assert review(client, a, sid).status_code == 409
    assert review(client, a, sid, accuracy="UNDETERMINABLE", policy="MATCH").status_code == 409
    assert review(client, a, sid, accuracy="UNDETERMINABLE", policy="UNDETERMINABLE").status_code == 201


def test_writer_provenance_failure_rolls_back_even_when_caught(app, monkeypatch):
    c = command(app, provenance="full")
    original = quality_provenance.persist

    def fail(*a, **kw):
        original(*a, **kw)
        raise RuntimeError("synthetic provenance storage failure")

    monkeypatch.setattr(quality_provenance, "persist", fail)
    with app.state.session_factory.begin() as s:
        with pytest.raises(RuntimeError):
            commit_automatic_reply(s, c)
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(reply_records)) == 0
        assert s.scalar(select(func.count()).select_from(messages).where(messages.c.final_reply)) == 0
        assert (
            s.scalar(select(automation_jobs.c.status).where(automation_jobs.c.job_id == str(c.job_id)))
            == "RUNNING"
        )


def test_parallel_reviews_one_revision_and_unchanged_material_detection(client, app):
    h, a = auth(client, app)
    r, c = confirmed(app, provenance="full")
    sid = select_sample(client, h, r["message_id"]).json()["sample_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda i: review(client, a, sid, key=f"quality-parallel-{i}"), range(2)))
    assert sorted(x.status_code for x in results) == [201, 409]
    with app.state.session_factory.begin() as s:
        s.execute(
            knowledge_documents.update()
            .where(knowledge_documents.c.document_id == str(c.provenance.evidence[0].document_id))
            .values(version=2)
        )
    d = client.post(
        f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "QUALITY_REVIEW"}
    ).json()
    assert d["material_state"] == "MATERIAL_CHANGED" and d["policies"][0]["body"] is None
    assert (
        review(
            client, a, sid, rev=2, reason="CORRECTION", key="quality-policy-changed", policy="MATCH"
        ).status_code
        == 409
    )
    with app.state.session_factory.begin() as s:
        s.execute(
            knowledge_documents.update()
            .where(knowledge_documents.c.document_id == str(c.provenance.evidence[0].document_id))
            .values(version=1, body="changed body with unchanged claimed hash")
        )
    d = client.post(
        f"{URL}/samples/{sid}/material", headers=a, json={"purpose_code": "QUALITY_REVIEW"}
    ).json()
    assert d["material_state"] == "MATERIAL_CHANGED" and d["policies"][0]["body"] is None
