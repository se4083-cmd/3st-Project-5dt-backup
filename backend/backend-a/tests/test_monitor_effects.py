"""Isolated synthetic PostgreSQL contracts, not actual B/Fabric integrations."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app import automation_monitor as monitor
from app.analytics_canonical import digest
from app.db import utcnow
from app.effect_models import effect_batches, effect_current
from app.effect_schemas import EffectPayload
from app.finalization import commit_automatic_reply
from app.model_constraints import user_team_scopes
from app.models import automation_jobs, tickets
from app.monitor_models import cycles, events
from app.resolution import WorkRejected
from app.seed import stable_id
from app.staff_models import automation_control
from tests.analytics_helpers import service_headers
from tests.conftest import login_as
from tests.quality_helpers import command, grant
from tests.test_voc_improvements import URL as VOC
from tests.test_voc_improvements import add_plan, admin, create, plan

EFFECT = "/api/v1/analytics/voc-effects/batches"
METRICS = "/api/v1/staff/quality/automation-metrics"
TEAM = stable_id("team")


def effect_fixture(client, app, **changes):
    h = admin(client, app)
    now = utcnow()
    implementation = now - timedelta(days=15)
    window = dict(
        implemented_at=implementation.isoformat(),
        before_start=(implementation - timedelta(days=14)).isoformat(),
        before_end=implementation.isoformat(),
        after_start=implementation.isoformat(),
        after_end=(implementation + timedelta(days=14)).isoformat(),
    )
    aid = create(client, h, plan=plan(**window))
    payload = dict(
        action_id=aid,
        plan_revision=1,
        product_id=stable_id("product"),
        issue_code="DAMAGED",
        scope_team_ids=[TEAM],
        origin="SYNTHETIC",
        **window,
        source_as_of=(now - timedelta(seconds=1)).isoformat(),
        generated_at=now.isoformat(),
        before_definition="VOC_EPISODE_V1",
        after_definition="VOC_EPISODE_V1",
        overlap="UNKNOWN",
        before=dict(
            inquiry_count=10,
            inquiry_coverage="1",
            sales_count=None,
            sales_coverage="0",
            inquiries_per_sale=None,
        ),
        after=dict(
            inquiry_count=5,
            inquiry_coverage="1",
            sales_count=None,
            sales_coverage="0",
            inquiries_per_sale=None,
        ),
        count_absolute_change=-5,
        count_relative_change="-0.5",
        rate_absolute_change=None,
        rate_relative_change=None,
        **changes,
    )
    return h, aid, submission(payload)


def submission(payload, bid=None):
    p = EffectPayload.model_validate(payload)
    return dict(batch_id=bid or str(uuid4()), payload=p.model_dump(mode="json"), payload_sha256=digest(p))


def stage_effect(client, app, body):
    svc = service_headers(app, ["voc-effects:receive", "voc-effects:publish"])
    r = client.post(EFFECT, headers=svc, json=body)
    assert r.status_code == 200, r.text
    bid = body["batch_id"]
    r = client.post(f"{EFFECT}/{bid}/validate", headers=svc)
    assert r.status_code == 200, r.text
    return svc, r.json()


def effect_read(client, h, aid, **q):
    r = client.get(f"{VOC}/{aid}/effects", headers=h, params=q)
    assert r.status_code == 200, r.text
    return r.json()


def test_effect_end_to_end_isolated_origins_and_idempotency(client, app):
    h, aid, b = effect_fixture(client, app)
    assert effect_read(client, h, aid)["reason"] == "NO_PUBLISHED_EFFECT_BATCH"
    svc, result = stage_effect(client, app, b)
    assert result["status"] == "VALIDATED" and result["validation"]["comparison_basis"] == "INQUIRY_COUNT"
    assert client.post(f"{EFFECT}/{b['batch_id']}/publish", headers=svc).status_code == 200
    d = effect_read(client, h, aid, origin="SYNTHETIC")
    assert d["availability"] == "AVAILABLE" and d["payload"]["before"]["inquiries_per_sale"] is None
    assert d["causal_effect"] == "NOT_ESTABLISHED" and "OVERLAP_UNKNOWN" in d["status_codes"]
    assert effect_read(client, h, aid)["availability"] == "UNAVAILABLE"
    assert client.post(EFFECT, headers=svc, json=b).json()["status"] == "SUCCEEDED"
    assert client.post(f"{EFFECT}/{b['batch_id']}/publish", headers=svc).status_code == 200
    changed = submission({**b["payload"], "overlap": "POSSIBLE"}, b["batch_id"])
    assert client.post(EFFECT, headers=svc, json=changed).status_code == 409
    assert client.get(f"{VOC}/{aid}/effects", headers=h).headers["Cache-Control"] == "no-store"
    with app.state.session_factory.begin() as s:
        with pytest.raises(DBAPIError), s.begin_nested():
            s.execute(effect_batches.update().values(payload={}))


@pytest.mark.parametrize(
    "bad,code",
    [
        ({"scope_team_ids": [str(uuid4())]}, "EXACT_SCOPE_MISMATCH"),
        ({"product_id": str(uuid4())}, "PRODUCT_MISMATCH"),
        ({"count_absolute_change": -7}, "CHANGE_ARITHMETIC_INVALID"),
        ({"count_relative_change": "0.5"}, "CHANGE_ARITHMETIC_INVALID"),
    ],
)
def test_effect_rejects_invalid_claims(client, app, bad, code):
    h, aid, b = effect_fixture(client, app)
    b = submission({**b["payload"], **bad})
    svc, d = stage_effect(client, app, b)
    assert d["status"] == "FAILED" and code in d["validation"]["codes"]
    assert client.post(f"{EFFECT}/{b['batch_id']}/publish", headers=svc).status_code == 409
    assert effect_read(client, h, aid, origin="SYNTHETIC")["availability"] == "UNAVAILABLE"


def test_effect_rates_zero_baseline_incomplete_definition_and_immature(client, app):
    h, aid, b = effect_fixture(client, app)
    p = b["payload"]
    p["before"].update(sales_count=100, sales_coverage="1", inquiries_per_sale="0.1")
    p["after"].update(sales_count=100, sales_coverage="1", inquiries_per_sale="0.05")
    p.update(rate_absolute_change="-0.05", rate_relative_change="-0.5")
    _, d = stage_effect(client, app, submission(p))
    assert d["validation"]["comparison_basis"] == "INQUIRIES_PER_SALE"
    p["before"].update(inquiry_count=0, inquiries_per_sale="0")
    p.update(
        count_absolute_change=5,
        count_relative_change=None,
        rate_absolute_change="0.05",
        rate_relative_change=None,
    )
    _, d = stage_effect(client, app, submission(p))
    assert "ZERO_BEFORE_BASELINE" in d["validation"]["status_codes"]
    p["before"].update(sales_count=0, inquiries_per_sale=None)
    p.update(rate_absolute_change=None, rate_relative_change=None)
    _, d = stage_effect(client, app, submission(p))
    assert "ZERO_SALES_DENOMINATOR" in d["validation"]["status_codes"]
    p.update(after_definition="NEW_DEFINITION", count_absolute_change=None, count_relative_change=None)
    p["after"].update(inquiry_coverage="0.5", inquiries_per_sale=None)
    p["source_as_of"] = p["after_start"]
    _, d = stage_effect(client, app, submission(p))
    assert d["status"] == "VALIDATED"
    assert {"SOURCE_INCOMPLETE", "DEFINITION_CHANGED", "OBSERVATION_IMMATURE"} <= set(
        d["validation"]["status_codes"]
    )


def test_effect_auth_scope_and_hash(client, app):
    h, aid, b = effect_fixture(client, app)
    for label in ["customer1", "agent"]:
        u = login_as(client, label)
        assert client.get(f"{VOC}/{aid}/effects", headers=u).status_code == 403
    service_headers(app)
    assert client.post(EFFECT, headers=h, json=b).status_code == 401
    assert client.post(EFFECT, headers=service_headers(app, ["analytics:receive"]), json=b).status_code == 403
    svc = service_headers(app, ["voc-effects:receive"])
    bad_hash = {**b, "payload_sha256": "0" * 64}
    assert client.post(EFFECT, headers=svc, json=bad_hash).status_code == 422
    operational = submission({**b["payload"], "origin": "OPERATIONAL"})
    assert client.post(EFFECT, headers=svc, json=operational).status_code == 403
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
    assert client.get(f"{VOC}/{aid}/effects", headers=h).status_code == 404


def test_effect_plan_revision_late_result_and_atomic_publish(client, app, monkeypatch):
    from app import voc_effects

    h, aid, b = effect_fixture(client, app)
    svc, _ = stage_effect(client, app, b)
    original = voc_effects.event

    def fail(*args):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(voc_effects, "event", fail)
    assert client.post(f"{EFFECT}/{b['batch_id']}/publish", headers=svc).status_code == 500
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(effect_current)) == 0
        assert s.scalar(select(effect_batches.c.status)) == "VALIDATED"
    monkeypatch.setattr(voc_effects, "event", original)
    assert client.post(f"{EFFECT}/{b['batch_id']}/publish", headers=svc).status_code == 200
    later = submission({**b["payload"], "generated_at": (utcnow() + timedelta(seconds=1)).isoformat()})
    stage_effect(client, app, later)
    assert client.post(f"{EFFECT}/{later['batch_id']}/publish", headers=svc).status_code == 200
    assert client.post(f"{EFFECT}/{b['batch_id']}/publish", headers=svc).status_code == 200
    assert effect_read(client, h, aid, origin="SYNTHETIC")["batch_id"] == later["batch_id"]
    old = submission(b["payload"])
    stage_effect(client, app, old)
    assert client.post(f"{EFFECT}/{old['batch_id']}/publish", headers=svc).status_code == 409
    window = {
        k: b["payload"][k]
        for k in ["implemented_at", "before_start", "before_end", "after_start", "after_end"]
    }
    assert add_plan(client, h, aid, **window).status_code == 201
    assert effect_read(client, h, aid, origin="SYNTHETIC")["availability"] == "UNAVAILABLE"
    assert effect_read(client, h, aid, origin="SYNTHETIC", plan_revision=1)["plan_is_current"] is False
    old = submission(b["payload"])
    _, d = stage_effect(client, app, old)
    assert "PLAN_NOT_CURRENT" in d["validation"]["codes"]


def monitored_command(app, **kw):
    c = command(app, **kw)
    with app.state.session_factory.begin() as s:
        t = (
            s.execute(
                select(tickets)
                .join(automation_jobs, automation_jobs.c.ticket_id == tickets.c.ticket_id)
                .where(automation_jobs.c.job_id == str(c.job_id))
            )
            .mappings()
            .one()
        )
        monitor.start_cycle(s, t["ticket_id"], 1, "AUTO", 1, utcnow(), origin=t["data_origin"])
        monitor.record(s, t["ticket_id"], 1, "ROUTED", 1, team_id=TEAM)
    return c, t["ticket_id"]


def diagnostic(client, app, **q):
    grant(app, "admin", "QUALITY_METRICS_READ")
    h = login_as(client, "admin")
    now = utcnow()
    r = client.get(
        METRICS,
        headers=h,
        params=dict(
            response_start=(now - timedelta(days=1)).isoformat(),
            response_end=(now + timedelta(seconds=1)).isoformat(),
            origin="SYNTHETIC",
            **q,
        ),
    )
    assert r.status_code == 200, r.text
    return r.json()


def worker_command(c, outcome="FAILED_HANDOFF"):
    return monitor.WorkerOutcome(
        job_id=c.job_id,
        cycle_no=1,
        expected_revision=1,
        lease_token=c.lease_token,
        worker_id=c.worker_id,
        automation_generation=1,
        outcome=outcome,
        reason_code="RETRY_EXHAUSTED",
    )


def test_prospective_cycle_commands_and_legacy_no_backfill(client, app):
    h = login_as(client, "customer1")
    r = client.post(
        "/api/v1/tickets",
        headers={**h, "Idempotency-Key": "monitor-create-001"},
        json={"message": "합성 문의"},
    )
    assert r.status_code == 201
    tid = r.json()["ticket_id"]
    assert (
        client.post(
            "/api/v1/tickets",
            headers={**h, "Idempotency-Key": "monitor-create-001"},
            json={"message": "합성 문의"},
        ).status_code
        == 200
    )
    r = client.post(
        f"/api/v1/tickets/{tid}/request-agent",
        headers={**h, "Idempotency-Key": "monitor-human-001"},
        json={"expected_revision": 1, "message": "합성 사람 요청", "reason_code": "CUSTOMER_REQUEST"},
    )
    assert r.status_code == 201, r.text
    with app.state.session_factory() as s:
        rows = list(s.execute(select(cycles).where(cycles.c.ticket_id == tid)).mappings())
        assert len(rows) == 2 and rows[1]["entry_mode"] == "HUMAN" and rows[1]["origin_auto_cycle_no"] == 1
        assert (
            s.scalar(
                select(func.count())
                .select_from(events)
                .where(events.c.ticket_id == tid, events.c.kind == "TRANSFER")
            )
            == 1
        )
    c = command(app)
    with app.state.session_factory.begin() as s:
        commit_automatic_reply(s, c)
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(cycles)) == 2


def test_worker_facts_require_same_transaction_transition_and_replay(client, app):
    c, tid = monitored_command(app)
    cmd = worker_command(c)
    with pytest.raises(DBAPIError), app.state.session_factory.begin() as s:
        monitor.record_worker_outcome(s, cmd, service_id="backend-b")
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(events).where(events.c.kind == "FAILED")) == 0
    with app.state.session_factory.begin() as s:
        out = monitor.record_worker_outcome(s, cmd, service_id="backend-b")
        assert out["recorded"]
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == str(c.job_id))
            .values(status="FAILED", lease_owner=None, lease_token=None, lease_until=None)
        )
        s.execute(
            tickets.update()
            .where(tickets.c.ticket_id == tid)
            .values(requested_mode="HUMAN", status="HANDOFF_PENDING", version=2)
        )
    with app.state.session_factory.begin() as s:
        assert monitor.record_worker_outcome(s, cmd, service_id="backend-b")["replayed"]
    d = diagnostic(client, app)
    assert d["auto_cycle_count"] == 1 and d["transferred_count"] == 1 and d["failed_fact_count"] == 1
    assert sum(d["statuses"].values()) == 1 and d["transfer_reasons"] == {"RETRY_EXHAUSTED": 1}
    assert d["safe_completion"]["rate"] is None
    customer = login_as(client, "customer1")
    reopened = client.post(
        f"/api/v1/tickets/{tid}/reopen",
        headers={**customer, "Idempotency-Key": "monitor-human-reopen"},
        json={"expected_revision": 2, "message": "합성 재문의"},
    )
    assert reopened.status_code == 201, reopened.text
    again = diagnostic(client, app)
    assert again["auto_cycle_count"] == again["transferred_count"] == 1
    assert again["human_entry_count_excluded"] == 0  # New HUMAN cycle has no recorded route.
    grant(app, "admin", "QUALITY_UNATTRIBUTED_MANAGE")
    assert diagnostic(client, app, include_unattributed=True)["human_entry_count_excluded"] == 1


@pytest.mark.parametrize("bad", ["cycle", "version", "lease", "owner", "generation", "paused", "expired"])
def test_worker_fact_fencing(app, bad):
    c, tid = monitored_command(app)
    cmd = worker_command(c)
    if bad in ["cycle", "version", "lease", "owner", "generation"]:
        cmd = cmd.model_copy(
            update={
                {
                    "cycle": "cycle_no",
                    "version": "expected_revision",
                    "lease": "lease_token",
                    "owner": "worker_id",
                    "generation": "automation_generation",
                }[bad]: {"cycle": 2, "version": 2, "lease": uuid4(), "owner": "other", "generation": 2}[bad]
            }
        )
    with app.state.session_factory.begin() as s:
        if bad == "paused":
            s.execute(automation_control.update().values(paused=True))
        if bad == "expired":
            s.execute(
                automation_jobs.update()
                .where(automation_jobs.c.job_id == str(c.job_id))
                .values(lease_until=utcnow() - timedelta(seconds=1))
            )
    with pytest.raises(WorkRejected), app.state.session_factory.begin() as s:
        monitor.record_worker_outcome(s, cmd, service_id="backend-b")


def test_monitor_completion_denominator_scope_and_immutable_history(client, app):
    c, tid = monitored_command(app)
    with app.state.session_factory.begin() as s:
        commit_automatic_reply(s, c)
    monitored_command(app)
    d = diagnostic(client, app)
    assert d["auto_cycle_count"] == 2 and d["automatic_completed_rate"] == 0.5 and d["transferred_rate"] == 0
    assert d["safe_observation_states"]["UNREVIEWED"] == 1
    assert d["legacy_current_auto_mode_untracked_count"] is None
    assert sum(d["statuses"].values()) == 2
    for role in ["agent", "customer1"]:
        grant(app, role, "QUALITY_METRICS_READ")
        assert (
            client.get(
                METRICS,
                headers=login_as(client, role),
                params={"response_start": utcnow().isoformat(), "response_end": utcnow().isoformat()},
            ).status_code
            == 403
        )
    with app.state.session_factory.begin() as s:
        with pytest.raises(DBAPIError), s.begin_nested():
            s.execute(events.update().values(reason_code="OTHER"))
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
    assert diagnostic(client, app)["auto_cycle_count"] == 0


@pytest.mark.parametrize(
    "state,kw",
    [
        ("NOT_AUTO_COMPLETED", {"completed": False}),
        ("ADVERSE_FOLLOWUP_OBSERVED", {"recontacted": True}),
        ("UNREVIEWED", {"reviewed": False}),
        ("REVIEW_NEGATIVE_OR_UNDETERMINABLE", {"positive": False}),
        ("OBSERVATION_IMMATURE", {"mature": False}),
        ("INCOMPLETE_OBSERVATION", {"reporting_complete": False}),
        ("PROVISIONALLY_OBSERVED_NOT_OPERATIONAL_CERTIFICATION", {}),
    ],
)
def test_development_safe_rule_is_not_operational_rate(state, kw):
    args = dict(
        completed=True,
        transferred=False,
        recontacted=False,
        reviewed=True,
        positive=True,
        mature=True,
        evidence_complete=True,
        reporting_complete=True,
    )
    assert monitor.evaluate_safe(**{**args, **kw}) == state


def test_unreported_B_snapshot_is_not_an_invented_transfer(client, app):
    c, tid = monitored_command(app)
    with app.state.session_factory.begin() as s:
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == str(c.job_id))
            .values(status="FAILED", lease_owner=None, lease_token=None, lease_until=None)
        )
        s.execute(
            tickets.update()
            .where(tickets.c.ticket_id == tid)
            .values(requested_mode="HUMAN", status="HANDOFF_PENDING", version=2)
        )
    d = diagnostic(client, app)
    assert d["transferred_count"] == 0 and d["failed_fact_count"] == 0
    assert d["unreported_current_human_state_count"] == d["unreported_current_terminal_state_count"] == 1
    assert d["recording_completeness"] == "PARTIAL_OBSERVED_FACTS_B_REPORTING_NOT_ATTESTED"


def test_retry_facts_do_not_create_new_cohort_and_unknown_reason(client, app):
    c, tid = monitored_command(app)
    with app.state.session_factory.begin() as s:
        s.execute(automation_jobs.update().where(automation_jobs.c.job_id == str(c.job_id)).values(attempt=1))
        cmd = worker_command(c, "RETRY")
        monitor.record_worker_outcome(s, cmd, service_id="backend-b")
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == str(c.job_id))
            .values(status="RETRY", lease_owner=None, lease_token=None, lease_until=None)
        )
    token = str(uuid4())
    with app.state.session_factory.begin() as s:
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == str(c.job_id))
            .values(
                status="RUNNING",
                attempt=2,
                lease_token=token,
                lease_owner=c.worker_id,
                lease_until=utcnow() + timedelta(minutes=5),
            )
        )
        cmd = worker_command(c).model_copy(update={"lease_token": UUID(token), "reason_code": "UNKNOWN"})
        monitor.record_worker_outcome(s, cmd, service_id="backend-b")
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == str(c.job_id))
            .values(status="FAILED", lease_owner=None, lease_token=None, lease_until=None)
        )
        s.execute(
            tickets.update()
            .where(tickets.c.ticket_id == tid)
            .values(requested_mode="HUMAN", status="HANDOFF_PENDING", version=2)
        )
    d = diagnostic(client, app)
    assert (
        d["auto_cycle_count"] == 1 and d["transferred_count"] == 1 and d["transfer_reasons"] == {"UNKNOWN": 1}
    )


def test_manual_review_observation_is_separate_from_safe_rate(client, app):
    from tests.quality_helpers import auth, review, select_sample

    h, reviewer = auth(client, app)
    c, _ = monitored_command(app, provenance="full")
    with app.state.session_factory.begin() as s:
        result = commit_automatic_reply(s, c)
    sid = select_sample(client, h, result["message_id"]).json()["sample_id"]
    assert review(client, reviewer, sid, policy="MATCH").status_code == 201
    d = diagnostic(client, app)
    assert d["safe_observation_states"] == {"OBSERVATION_IMMATURE": 1}
    assert d["safe_completion"]["availability"] == "UNAVAILABLE"
    assert d["safe_completion"]["rate"] is None


def test_effect_owner_change_and_scope_recheck(client, app):
    from app.models import followup_actions
    from tests.phase3_helpers import staff_user

    h, aid, body = effect_fixture(client, app)
    svc, _ = stage_effect(client, app, body)
    assert client.post(f"{EFFECT}/{body['batch_id']}/publish", headers=svc).status_code == 200
    other = stable_id("effect-other-team")
    staff_user(app, "effect-other-agent", team_id=other)
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=other))
        s.execute(
            followup_actions.update()
            .where(followup_actions.c.action_id == aid)
            .values(owner_team_id=other, owner_user_id=None)
        )
    assert effect_read(client, h, aid, origin="SYNTHETIC")["reason"] == "PLAN_RECONFIRM_REQUIRED"
    with app.state.session_factory.begin() as s:
        s.execute(
            user_team_scopes.delete().where(
                user_team_scopes.c.user_id == stable_id("admin"), user_team_scopes.c.team_id == TEAM
            )
        )
    assert client.get(f"{VOC}/{aid}/effects", headers=h, params={"origin": "SYNTHETIC"}).status_code == 404


def test_effect_concurrent_publication_keeps_newest_pointer(client, app):
    from concurrent.futures import ThreadPoolExecutor

    h, aid, b = effect_fixture(client, app)
    svc, _ = stage_effect(client, app, b)
    newer = submission({**b["payload"], "generated_at": (utcnow() + timedelta(seconds=1)).isoformat()})
    stage_effect(client, app, newer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda bid: client.post(f"{EFFECT}/{bid}/publish", headers=svc).status_code,
                [b["batch_id"], newer["batch_id"]],
            )
        )
    assert results[1] == 200 and results[0] in {200, 409}
    assert effect_read(client, h, aid, origin="SYNTHETIC")["batch_id"] == newer["batch_id"]


def test_recording_delay_rechecks_expired_lease_and_rolls_back(app, monkeypatch):
    c, tid = monitored_command(app)
    original = monitor.record

    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setattr(monitor, "utcnow", lambda: utcnow() + timedelta(hours=1))
        return result

    monkeypatch.setattr(monitor, "record", delayed)
    with pytest.raises(WorkRejected, match="INVALID_LEASE"), app.state.session_factory.begin() as s:
        monitor.record_worker_outcome(s, worker_command(c), service_id="backend-b")
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(events).where(events.c.kind == "FAILED")) == 0
