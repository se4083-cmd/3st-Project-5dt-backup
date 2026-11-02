"""Real-HTTP acceptance scenario; internal calls here are explicit test doubles."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import jwt
from sqlalchemy import select

from app import audit, repository
from app.analytics_auth import AUDIENCE, ISSUER
from app.analytics_canonical import canonical_submission, digest
from app.analytics_schemas import Submission
from app.db import utcnow
from app.finalization import AutomaticReply, commit_automatic_reply
from app.jobs import claim_jobs
from app.model_constraints import user_team_scopes
from app.models import assignments, automation_jobs, messages, tickets, users
from app.resolution import WorkRejected, lock_resolution_gate
from app.seed import stable_id
from scripts.prepare_analytics_fixture import FIXTURE_TEAMS, prepare

PRIVATE = "LOCAL_HTTP_PRIVATE_NOTE_SENTINEL"
CUSTOMER_TEXT = "로컬 합성 문의 검증"
FIXED_REPLY = "로컬 고정 합성 답변이며 실제 엔진 처리 결과가 아닙니다."


def expect(condition, code):
    if not condition:
        raise RuntimeError(code)  # no submitted payload/credentials/response body in errors


def clone_staff(factory, label, source, role, teams):
    uid = stable_id(label)
    with factory.begin() as session:
        row = dict(
            session.execute(select(users).where(users.c.user_id == stable_id(source))).mappings().one()
        )
        row.update(
            user_id=uid,
            login_name=f"dev-{label}@example.test",
            role=role,
            team_id=teams[0] if role == "AGENT" else None,
            allowed_team_ids=teams,
        )
        session.execute(users.insert().values(**row))
        for team in teams:
            session.execute(user_team_scopes.insert().values(user_id=uid, team_id=team))
    return uid


def assign_fixture(factory, tid, agent_id):
    """HANDOFF claim + fixed assignment fixture, not team selection/B engine."""
    with factory.begin() as session:
        job = next(
            j
            for j in claim_jobs(session, "local-routing-fixture", job_kind="HANDOFF")
            if j["ticket_id"] == tid
        )
    with factory.begin() as session:
        ticket = (
            session.execute(select(tickets).where(tickets.c.ticket_id == tid).with_for_update())
            .mappings()
            .one()
        )
        from app.exception_queue import RouteCommand, record_queue_route
        from app.staff_models import queue_routes

        route_revision = (
            session.scalar(
                select(queue_routes.c.revision).where(
                    queue_routes.c.ticket_id == tid, queue_routes.c.cycle_no == ticket["cycle_no"]
                )
            )
            or 0
        )
        record_queue_route(
            session,
            tid,
            RouteCommand(
                expected_revision=ticket["version"],
                cycle_no=ticket["cycle_no"],
                expected_route_revision=route_revision,
                team_id=stable_id("team"),
            ),
            service_id="local-routing-fixture",
        )
        current = (
            session.execute(
                select(automation_jobs).where(automation_jobs.c.job_id == job["job_id"]).with_for_update()
            )
            .mappings()
            .one()
        )
        expect(
            current["lease_token"] == job["lease_token"]
            and ticket["version"] == job["expected_ticket_version"]
            and ticket["cycle_no"] == job["cycle_no"]
            and current["lease_until"] > utcnow(),
            "FIXTURE_LEASE_INVALID",
        )
        session.execute(
            tickets.update()
            .where(tickets.c.ticket_id == tid)
            .values(
                team_id=stable_id("team"),
                category="DELIVERY",
                status="IN_PROGRESS",
                version=ticket["version"] + 1,
            )
        )
        session.execute(
            assignments.insert().values(
                assignment_id=str(uuid4()),
                ticket_id=tid,
                cycle_no=ticket["cycle_no"],
                team_id=stable_id("team"),
                agent_id=agent_id,
                assigned_at=utcnow(),
                reason_code="LOCAL_TEST_FIXTURE_ONLY",
            )
        )
        session.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == job["job_id"])
            .values(status="HANDED_OFF", lease_token=None, lease_owner=None, lease_until=None)
        )
        audit.record(session, None, "TEST_ASSIGNMENT_FIXTURE", "TICKET", tid, service="local-http-test")


def human_gate(factory, tid, uid, *, blocked):
    try:
        with factory.begin() as session:
            current = session.execute(select(tickets).where(tickets.c.ticket_id == tid)).mappings().one()
            user = repository.get_user(session, uid)
            ticket = lock_resolution_gate(
                session,
                tid,
                expected_revision=current["version"],
                cycle_no=current["cycle_no"],
                mode="HUMAN",
                human_user=user,
            )
            expect(not blocked, "BLOCKER_NOT_ENFORCED")
            # Test-only final writer after the common gate, not the B human response engine.
            session.execute(
                messages.insert().values(
                    message_id=str(uuid4()),
                    ticket_id=tid,
                    cycle_no=ticket["cycle_no"],
                    role="AGENT",
                    direction="OUT",
                    visibility="PUBLIC",
                    body=FIXED_REPLY,
                    final_reply=True,
                )
            )
            session.execute(
                tickets.update()
                .where(tickets.c.ticket_id == tid)
                .values(
                    status="RESOLVED",
                    resolution_mode="HUMAN",
                    resolved_at=utcnow(),
                    version=ticket["version"] + 1,
                )
            )
            audit.record(
                session, uid, "TEST_EXPLICIT_HUMAN_RESOLUTION", "TICKET", tid, service="local-http-test"
            )
    except WorkRejected as exc:
        expect(blocked and exc.code == "BLOCKING_FOLLOWUP", "UNEXPECTED_HUMAN_GATE_REJECTION")


def run(client, factory, env, fixture_dir):
    checks = []
    examples = {}

    def request(method, path, *, status=200, **kwargs):
        response = client.request(method, "/api/v1" + path, **kwargs)
        if response.status_code != status:
            # Only a route label/status, no UUIDs, submitted text, headers or body.
            import re

            route = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27,}", "id", path).replace("/", "_").upper()
            raise RuntimeError(f"HTTP_{method}{route}_EXPECTED_{status}_GOT_{response.status_code}")
        return response.json()

    def login(label):
        result = request(
            "POST",
            "/auth/login",
            json={"login_name": f"dev-{label}@example.test", "password": env["DEV_SEED_PASSWORD"]},
        )
        return {"Authorization": "Bearer " + result["access_token"]}

    def post(path, headers, body, key, status=201):
        return request("POST", path, status=status, headers={**headers, "Idempotency-Key": key}, json=body)

    own, other, agent, admin = (login(k) for k in ("customer1", "customer2", "agent", "admin"))
    order = request("GET", "/orders", headers=own)["items"][0]
    body = {"order_id": order["order_id"], "message": CUSTOMER_TEXT}
    receipt = post("/tickets", own, body, "http-ticket-001")
    tid = receipt["ticket_id"]
    expect(post("/tickets", own, body, "http-ticket-001", 200) == receipt, "CREATE_REPLAY_CHANGED")
    post("/tickets", own, {**body, "message": "로컬 변경 요청"}, "http-ticket-001", 409)
    request("GET", f"/tickets/{tid}", status=404, headers=other)
    request("GET", f"/orders/{order['order_id']}", status=404, headers=other)
    checks += ["login_order_ticket", "idempotent_replay_and_conflict", "cross_customer_denial"]
    with factory.begin() as session:
        job = next(j for j in claim_jobs(session, "local-fixed-auto") if j["ticket_id"] == tid)
    with factory.begin() as session:
        commit_automatic_reply(
            session,
            AutomaticReply(
                job_id=job["job_id"],
                lease_token=job["lease_token"],
                worker_id="local-fixed-auto",
                cycle_no=job["cycle_no"],
                expected_revision=job["expected_ticket_version"],
                message=FIXED_REPLY,
            ),
        )
    detail = request("GET", f"/tickets/{tid}", headers=own)
    expect(detail["stage"] == "COMPLETED", "AUTO_FIXED_RESPONSE_NOT_VISIBLE")
    reopened = post(
        f"/tickets/{tid}/reopen",
        own,
        {"expected_revision": detail["revision"], "message": CUSTOMER_TEXT},
        "http-reopen-001",
    )
    handoff = post(
        f"/tickets/{tid}/request-agent",
        own,
        {
            "expected_revision": reopened["revision"],
            "message": CUSTOMER_TEXT,
            "reason_code": "CUSTOMER_REQUEST",
        },
        "http-handoff-001",
    )
    expect(handoff["handling_mode"] == "HUMAN", "HUMAN_PATH_NOT_SET")
    assign_fixture(factory, tid, stable_id("agent"))
    created = post(
        "/staff/followups",
        agent,
        {
            "ticket_id": tid,
            "owner_team_id": stable_id("team"),
            "owner_user_id": stable_id("agent"),
            "kind": "LOCAL_CHECK",
            "public_note": "로컬 공개 후속",
            "internal_note": PRIVATE,
            "blocks_resolution": True,
        },
        "http-followup-001",
    )
    aid = created["action_id"]
    detail = request("GET", f"/tickets/{tid}", headers=own)
    post(
        f"/tickets/{tid}/reopen",
        own,
        {"expected_revision": detail["revision"], "message": CUSTOMER_TEXT},
        "http-reopen-human-002",
    )
    request("GET", f"/staff/followups/{aid}", headers=agent, status=404)
    queue = request("GET", "/staff/followups", headers=admin)
    expect(
        any(r["action_id"] == aid and r["needs_handover"] for r in queue["items"]),
        "ORPHAN_ACTION_MISSING_FROM_QUEUE",
    )
    next_uid = clone_staff(factory, "local-agent2", "agent", "AGENT", [stable_id("team")])
    next_agent = login("local-agent2")
    assign_fixture(factory, tid, next_uid)
    request(
        "POST",
        f"/staff/followups/{aid}/status",
        headers=next_agent,
        json={"expected_revision": 1, "status": "DONE"},
        status=409,
    )
    adopted = request(
        "PATCH",
        f"/staff/followups/{aid}",
        headers=next_agent,
        json={"expected_revision": 1, "owner_user_id": next_uid},
    )
    expect(adopted["responsibility_cycle_no"] > adopted["cycle_no"], "ORIGIN_CYCLE_NOT_PRESERVED")
    human_gate(factory, tid, next_uid, blocked=True)
    public = request("GET", f"/followups/{aid}", headers=own)
    expect(
        "internal_note" not in public and "owner_user_id" not in public and PRIVATE not in str(public),
        "PUBLIC_DTO_LEAK",
    )
    # A second same-customer ticket is outside this agent's assignment scope.
    hidden = post("/tickets", own, {"message": CUSTOMER_TEXT}, "http-unassigned-001")
    customer = stable_id("customer1/profile")
    purpose = {"purpose_code": "ACTIVE_SUPPORT"}
    overview = request("POST", f"/staff/customers/{customer}/360", headers=next_agent, json=purpose)
    expect(
        overview["total_ticket_count"] == 1 and overview["recent_tickets"][0]["ticket_id"] == tid,
        "CUSTOMER360_SCOPE_LEAK",
    )
    expect(overview["summary_contract"]["status"] == "NOT_GENERATED", "SUMMARY_CLAIMED_AI")
    request("GET", f"/tickets/{hidden['ticket_id']}", headers=next_agent, status=404)
    request("POST", f"/staff/customers/{customer}/360", headers=own, json=purpose, status=403)
    done = request(
        "POST",
        f"/staff/followups/{aid}/status",
        headers=next_agent,
        json={"expected_revision": adopted["revision"], "status": "DONE"},
    )
    expect(
        done["status"] == "DONE" and request("GET", f"/tickets/{tid}", headers=own)["stage"] == "IN_SUPPORT",
        "FOLLOWUP_COMPLETION_AUTO_RESOLVED",
    )
    human_gate(factory, tid, next_uid, blocked=False)
    expect(
        request("GET", f"/tickets/{tid}", headers=own)["stage"] == "COMPLETED", "EXPLICIT_RESOLUTION_FAILED"
    )
    checks += [
        "fixed_auto_reply_common_commit",
        "reopen_and_human_handoff",
        "test_handoff_claim_assignment",
        "followup_preservation_takeover_done",
        "mandatory_followup_resolution_gate",
        "explicit_test_human_resolution",
        "scoped_customer360",
        "public_internal_dto_separation",
    ]
    examples["ticket_receipt"] = receipt
    examples["followup_public_fields"] = sorted(public)
    # No internal note or message body in stored examples.
    examples["customer360_counts"] = {
        k: overview[k] for k in ("total_ticket_count", "unresolved_ticket_count", "followup_count")
    }

    url = "/admin/analytics"
    expect(
        request("GET", url + "/voc/top", headers=admin)["reason"] == "NO_PUBLISHED_BATCH",
        "INITIAL_BATCH_NOT_EMPTY",
    )
    fixture = prepare(fixture_dir)
    fixture["manifest"]["batch_id"] = str(uuid4())
    h = {
        "Authorization": "Bearer "
        + jwt.encode(
            {
                "sub": "local-synthetic-publisher",
                "iss": ISSUER,
                "aud": AUDIENCE,
                "iat": utcnow(),
                "nbf": utcnow(),
                "exp": utcnow() + timedelta(minutes=5),
                "permissions": ["analytics:receive", "analytics:publish"],
            },
            env["ANALYTICS_SERVICE_SECRET"],
            algorithm="HS256",
        )
    }
    bid = fixture["manifest"]["batch_id"]
    request("POST", "/analytics/batches", headers=admin, json=fixture, status=401)
    request("POST", "/analytics/batches", headers=h, json=fixture)
    valid = request("POST", f"/analytics/batches/{bid}/validate", headers=h)
    expect(valid["validation_passed"], "LOCAL_BATCH_VALIDATION_FAILED")
    request("POST", f"/analytics/batches/{bid}/publish", headers=h)
    # Explicit permission fixture only; not an authorization bypass endpoint.
    with factory.begin() as session:
        for team in FIXTURE_TEAMS.values():
            session.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=team))
    clone_staff(factory, "local-limited-admin", "admin", "ADMIN", [FIXTURE_TEAMS["T1"]])
    limited = login("local-limited-admin")
    params = [("team_ids", team) for team in FIXTURE_TEAMS.values()]
    top = request("GET", url + "/voc/top", headers=admin, params=params)
    expect(
        top["meta"]["scope_key"] == "ALL4"
        and top["meta"]["source"] == "LOCAL_SYNTHETIC"
        and bool(top["items"]),
        "TOP10_SCOPE_FAILED",
    )
    pid = top["items"][0]["product_id"]
    fixed = params + [("batch_id", bid)]
    product = request("GET", url + f"/products/{pid}", headers=admin, params=fixed)
    expect(
        product["meta"]["batch_id"] == bid and all(r["scope_key"] == "ALL4" for r in product["trend"]),
        "PRODUCT_TREND_SCOPE_FAILED",
    )
    kpi = request("GET", url + "/kpi", headers=admin, params=fixed)
    expect(kpi["metrics"]["reopened"]["availability"] == "UNAVAILABLE", "UNSAFE_KPI_EXPOSED")
    subset = request("GET", url + "/voc/top", headers=limited)
    expect(subset["meta"]["scope_key"] == "T1", "SUBSET_SCOPE_FAILED")
    for path in ("/voc/top", "/voc/unavailable", "/kpi", f"/products/{pid}"):
        request("GET", url + path, headers=limited, params=fixed, status=403)
    request("GET", url + "/voc/top", headers=agent, status=403)
    unavailable = request("GET", url + "/voc/unavailable", headers=admin, params=fixed)
    expect(
        all(r["score"] is None and r["rank"] is None for r in unavailable["items"]),
        "NONELIGIBLE_SCORE_NOT_NULL",
    )
    invalid = deepcopy(fixture)
    invalid["manifest"]["batch_id"] = str(uuid4())
    invalid["manifest"]["payload_checksums"]["analytics_daily"] = "0" * 64
    badid = invalid["manifest"]["batch_id"]
    request("POST", "/analytics/batches", headers=h, json=invalid)
    expect(
        request("POST", f"/analytics/batches/{badid}/validate", headers=h)["status"] == "FAILED",
        "BAD_BATCH_ACCEPTED",
    )
    request("POST", f"/analytics/batches/{badid}/publish", headers=h, status=409)
    expect(
        request("GET", url + "/voc/top", headers=admin, params=params)["meta"]["batch_id"] == bid,
        "FAILED_BATCH_REPLACED_CURRENT",
    )
    checks += [
        "local_service_auth",
        "synthetic_receive_validate_publish",
        "admin_kpi_top10_detail_trend",
        "exact_subset_and_scope_denial",
        "noneligible_nulls",
        "failed_batch_keeps_previous_success",
    ]
    examples["analytics_meta"] = top["meta"]
    from tests.http_phase6 import run_phase6

    phase6_checks, phase6_examples = run_phase6(factory, request, login, post, own, agent, admin)
    checks += phase6_checks
    examples.update(phase6_examples)
    from tests.http_phase7 import run_phase7

    phase7_checks, phase7_examples = run_phase7(factory, request, admin, agent, own)
    checks += phase7_checks
    examples.update(phase7_examples)
    from tests.http_review_fixes import run_review_fixes

    review_checks, review_examples = run_review_fixes(factory, request, post, login, own, admin)
    checks += review_checks
    examples.update(review_examples)
    # Local request file only; contains no customer IDs, keys, tickets or text.
    canonical = canonical_submission(Submission.model_validate(fixture))
    return {
        "result": "PASS",
        "source": "LOCAL_SYNTHETIC",
        "checks": checks,
        "examples": examples,
        "canonical_content_hash": digest(canonical),
        "engines_executed": [],
        "test_doubles": [
            "fixed automatic reply",
            "assignment fixture",
            "human gate + test final writer",
            "provided synthetic analytics",
        ],
    }
