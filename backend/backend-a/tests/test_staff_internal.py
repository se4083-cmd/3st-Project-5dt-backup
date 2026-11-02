from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import audit
from app.db import utcnow
from app.models import (
    ai_suggestions,
    approvals,
    assignments,
    audit_events,
    tickets,
)
from app.seed import stable_id
from tests.conftest import login_as
from tests.phase3_helpers import staff_user
from tests.phase6_helpers import BASE, internal_fixture
from tests.test_flow import submit
from tests.test_ticket_commands import action


def detail(client, tid, h, **body):
    return client.post(
        BASE + f"/tickets/{tid}/internal", headers=h, json={"purpose_code": "ACTIVE_SUPPORT", **body}
    )


def test_internal_allowlist_synthetic_and_customer_schema_separation(client, headers, app):
    tid, sid, aid, did, rid = internal_fixture(client, headers, app)
    h = login_as(client, "agent")
    response = detail(client, tid, h)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["material_status"] == "SYNTHETIC_ONLY"
    assert data["customer_ref"] == stable_id("customer1/profile")
    p = data["current_proposals"][0]
    assert p["record_state"] == "SYNTHETIC_HISTORY" and p["evidence"][0]["document_id"] == did
    assert p["masked_order"]["masked_order_ref"].startswith("****")
    assert p["approvals"][0]["record_state"] == "SYNTHETIC_HISTORY"
    assert p["approvals"][0]["usable_for_execution"] is False and p["draft_exposed"] is False
    assert "PRIVATE_" not in response.text and "raw_prompt" not in response.text
    assert detail(client, tid, headers).status_code == 403
    public = client.get("/api/v1/tickets/" + tid, headers=headers)
    assert "customer_ref" not in public.text
    assert (
        "current_proposals" not in public.text and "gate" not in public.text and "PRIVATE_" not in public.text
    )
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    assert not {"current_proposals", "gate_results", "approvals"} & set(schema["TicketDetail"]["properties"])


@pytest.mark.parametrize("case", ["ended", "other_team", "old_cycle"])
def test_internal_current_assignment_scope(client, headers, app, case):
    tid, *_ = internal_fixture(client, headers, app)
    if case == "ended":
        with app.state.session_factory.begin() as s:
            s.execute(assignments.update().where(assignments.c.ticket_id == tid).values(ended_at=utcnow()))
    elif case == "other_team":
        staff_user(app, "internal-other", team_id=stable_id("internal-other-team"))
        with app.state.session_factory.begin() as s:
            s.execute(
                tickets.update()
                .where(tickets.c.ticket_id == tid)
                .values(team_id=stable_id("internal-other-team"))
            )
    else:
        assert action(client, headers, tid).status_code == 201
    assert detail(client, tid, login_as(client, "agent")).status_code == 404
    if case == "other_team":
        assert detail(client, tid, login_as(client, "admin")).status_code == 404


def test_current_staff_can_distinguish_past_cycle_and_missing_data(client, headers, app):
    tid, *_ = internal_fixture(client, headers, app)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(cycle_no=2, version=2))
        s.execute(assignments.update().where(assignments.c.ticket_id == tid).values(cycle_no=2))
    h = login_as(client, "agent")
    assert detail(client, tid, h).json()["material_status"] == "MISSING"
    body = detail(client, tid, h, include_history=True).json()
    assert body["current_proposals"] == [] and body["historical_proposals"][0]["cycle_no"] == 1
    assert all(a["usable_for_execution"] is False for a in body["historical_proposals"][0]["approvals"])
    assert detail(client, tid, h, purpose_code="QUALITY_REVIEW").status_code == 403
    assert detail(client, tid, login_as(client, "admin"), purpose_code="QUALITY_REVIEW").status_code == 200
    assert client.post(BASE + f"/tickets/{tid}/internal", headers=h, json={}).status_code == 422


@pytest.mark.parametrize(
    "case",
    [
        "approval_ticket",
        "approval_cycle",
        "approval_hash",
        "rule_version",
        "snapshot_order",
        "policy_version",
        "policy_hash",
        "gate_type",
        "version_secret",
    ],
)
def test_nested_linkage_and_untrusted_jsonb_are_restricted(client, headers, app, case):
    tid, sid, aid, did, rid = internal_fixture(client, headers, app, synthetic=False)
    other = (
        submit(client, headers, key="other-link-ticket").json()["ticket_id"]
        if case == "approval_ticket"
        else None
    )
    with app.state.session_factory.begin() as s:
        sig = dict(
            s.execute(select(ai_suggestions).where(ai_suggestions.c.suggestion_id == sid)).mappings().one()
        )
        if case == "approval_ticket":
            s.execute(approvals.update().where(approvals.c.approval_id == aid).values(ticket_id=other))
        elif case == "approval_cycle":
            s.execute(approvals.update().where(approvals.c.approval_id == aid).values(cycle_no=2))
        elif case == "approval_hash":
            s.execute(approvals.update().where(approvals.c.approval_id == aid).values(content_hash="c" * 64))
        elif case == "rule_version":
            s.execute(
                ai_suggestions.update().where(ai_suggestions.c.suggestion_id == sid).values(rule_version=9)
            )
        elif case == "snapshot_order":
            s.execute(
                ai_suggestions.update()
                .where(ai_suggestions.c.suggestion_id == sid)
                .values(
                    order_snapshot={
                        "order_id": stable_id("customer2/order/0"),
                        "version": 1,
                        "password": "PRIVATE_OMITTED",
                    }
                )
            )
        elif case in {"policy_version", "policy_hash"}:
            refs = sig["evidence_refs"]
            refs[0]["version" if case == "policy_version" else "content_hash"] = (
                999 if case == "policy_version" else "0" * 64
            )
            s.execute(
                ai_suggestions.update()
                .where(ai_suggestions.c.suggestion_id == sid)
                .values(evidence_refs=refs)
            )
        elif case == "gate_type":
            s.execute(
                ai_suggestions.update()
                .where(ai_suggestions.c.suggestion_id == sid)
                .values(
                    gate_results={
                        "ownership_valid": "PRIVATE_SECRET",
                        "policy_valid": {"password": "PRIVATE_PASSWORD"},
                    }
                )
            )
        elif case == "version_secret":
            s.execute(
                ai_suggestions.update()
                .where(ai_suggestions.c.suggestion_id == sid)
                .values(prompt_version="postgresql://PRIVATE_SECRET")
            )
    r = detail(client, tid, login_as(client, "agent"))
    assert r.status_code == 200, r.text
    assert "PRIVATE_" not in r.text
    p = r.json()["current_proposals"][0]
    if case.startswith("approval_"):
        assert p["approvals"] == [] and p["invalid_approval_links"]
    elif case == "rule_version":
        assert p["record_state"] == "INVALID_LINK" and p["evidence"] == []
    elif case == "snapshot_order":
        assert p["masked_order"] is None and p["order_snapshot_state"] == "INVALID_LINK"
    elif case.startswith("policy_"):
        assert p["evidence"] == [] and p["evidence_state"] == "PARTIAL_OR_INVALID"
    elif case == "gate_type":
        assert p["gates"]["ownership_valid"] is None and p["gates"]["policy_valid"] is None
    elif case == "version_secret":
        assert p["prompt_version"] is None


@pytest.mark.parametrize(
    "case,state", [("expired", "EXPIRED"), ("stale", "STALE_TICKET_VERSION"), ("current", "CURRENT_RECORDED")]
)
def test_approval_display_is_not_execution_authority(client, headers, app, case, state):
    tid, sid, aid, *_ = internal_fixture(client, headers, app, synthetic=False)
    with app.state.session_factory.begin() as s:
        if case == "expired":
            s.execute(
                approvals.update()
                .where(approvals.c.approval_id == aid)
                .values(expires_at=utcnow() - timedelta(seconds=1))
            )
        elif case == "stale":
            s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(version=2))
    r = detail(client, tid, login_as(client, "agent")).json()
    a = r["current_proposals"][0]["approvals"][0]
    assert a["record_state"] == state and a["usable_for_execution"] is False


def test_internal_purpose_audit_is_atomic(client, headers, app, monkeypatch):
    tid, *_ = internal_fixture(client, headers, app)
    h = login_as(client, "agent")
    assert detail(client, tid, h).status_code == 200
    with app.state.session_factory() as s:
        before = s.scalar(
            select(func.count()).select_from(audit_events).where(audit_events.c.action == "READ_STAFF_TICKET")
        )
    original = audit.record

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        if args[2] == "READ_STAFF_TICKET":
            raise RuntimeError("injected")

    monkeypatch.setattr(audit, "record", fail)
    assert detail(client, tid, h).status_code == 500
    with app.state.session_factory() as s:
        assert (
            s.scalar(
                select(func.count())
                .select_from(audit_events)
                .where(audit_events.c.action == "READ_STAFF_TICKET")
            )
            == before
        )
