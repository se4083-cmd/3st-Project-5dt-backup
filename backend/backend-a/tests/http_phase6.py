"""Phase6 HTTP acceptance with explicitly scoped local DB fixtures only."""

from sqlalchemy import func, select

from app.exception_queue import RouteCommand, record_queue_route
from app.finalization import AutomaticReply, WorkRejected, commit_automatic_reply
from app.jobs import claim_jobs
from app.models import automation_rules, tickets
from app.seed import stable_id
from app.staff_models import staff_permissions
from tests.phase6_helpers import material_fixture


def run_phase6(factory, request, login, post, own, agent, admin):
    # Existing ADMIN/AGENT has no explicit capability before fixture grants.
    request("GET", "/staff/exception-queue", headers=admin, status=403)
    request("GET", "/staff/automation-control", headers=admin, status=403)
    with factory.begin() as s:
        for permission in (
            "EXCEPTION_QUEUE_READ",
            "UNROUTED_QUEUE_READ",
            "AUTOMATION_READ",
            "AUTOMATION_STOP",
            "AUTOMATION_RESUME",
        ):
            s.execute(staff_permissions.insert().values(user_id=stable_id("admin"), permission=permission))
        s.execute(
            staff_permissions.insert().values(user_id=stable_id("agent"), permission="EXCEPTION_QUEUE_READ")
        )
    tid = post(
        "/tickets",
        own,
        {"order_id": stable_id("customer1/order/0"), "message": "로컬 합성 문의 검증"},
        "phase6-http-ticket",
    )["ticket_id"]
    with factory.begin() as s:
        # Fixed classification fixture only; no AI classifier is called.
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(category="DELIVERY"))
    unrouted = request("GET", "/staff/exception-queue", headers=admin, params={"queue_scope": "UNROUTED"})
    if not any(r["ticket_id"] == tid and r["route_team_id"] is None for r in unrouted["items"]):
        raise RuntimeError("HTTP_UNROUTED_FIXTURE_MISSING")
    request("GET", "/staff/exception-queue", headers=agent, params={"queue_scope": "UNROUTED"}, status=403)
    with factory.begin() as s:
        record_queue_route(
            s,
            tid,
            RouteCommand(
                expected_revision=1, cycle_no=1, expected_route_revision=0, team_id=stable_id("team")
            ),
            service_id="local-http-route-fixture",
        )
    queue = request("GET", "/staff/exception-queue", headers=agent)
    counts = request("GET", "/staff/exception-queue/counts", headers=agent)
    if queue["total"] != counts["total"] or not any(r["ticket_id"] == tid for r in queue["items"]):
        raise RuntimeError("HTTP_ROUTED_QUEUE_MISMATCH")
    purpose = {"purpose_code": "ACTIVE_SUPPORT"}
    request("POST", f"/staff/tickets/{tid}/internal", headers=agent, json=purpose, status=404)
    request(
        "POST",
        f"/staff/customers/{stable_id('customer1/profile')}/360",
        headers=agent,
        json=purpose,
        status=404,
    )
    with factory.begin() as s:
        job = next(j for j in claim_jobs(s, "phase6-inflight-fixture") if j["ticket_id"] == tid)
    command = AutomaticReply(
        job_id=job["job_id"],
        cycle_no=job["cycle_no"],
        expected_revision=job["expected_ticket_version"],
        worker_id="phase6-inflight-fixture",
        lease_token=job["lease_token"],
        automation_generation=job["automation_generation"],
        message="로컬 고정 합성 답변이며 실제 엔진 처리 결과가 아닙니다.",
    )
    control = "/staff/automation-control"
    stopped = request(
        "POST",
        control + "/stop",
        headers=admin,
        json={"expected_revision": 1, "reason_code": "SAFETY_INCIDENT"},
    )
    request(
        "POST",
        control + "/stop",
        headers=admin,
        json={"expected_revision": 1, "reason_code": "SAFETY_INCIDENT"},
        status=409,
    )
    with factory.begin() as s:
        if claim_jobs(s, "paused-http-worker"):
            raise RuntimeError("HTTP_PAUSED_CLAIM_ALLOWED")

    def rejected(code):
        try:
            with factory.begin() as s:
                commit_automatic_reply(s, command)
        except WorkRejected as exc:
            if exc.code == code:
                return
        raise RuntimeError("HTTP_CONTROL_FENCE_NOT_ENFORCED")

    rejected("AUTOMATION_PAUSED")
    paused = request("GET", "/staff/exception-queue", headers=agent)
    if next(r for r in paused["items"] if r["ticket_id"] == tid)["automatic_state"] != "PAUSED":
        raise RuntimeError("HTTP_PAUSED_WORK_HIDDEN")
    request(
        "POST",
        control + "/resume",
        headers=admin,
        json={"expected_revision": 2, "stopped_revision": 1, "reason_code": "INCIDENT_RESOLVED"},
        status=409,
    )
    request(
        "POST",
        control + "/resume",
        headers=admin,
        json={"expected_revision": 2, "stopped_revision": 2, "reason_code": "INCIDENT_RESOLVED"},
    )
    rejected("AUTOMATION_GENERATION_CHANGED")
    request(
        "POST",
        control + "/stop",
        headers=admin,
        json={"expected_revision": 3, "reason_code": "OPERATOR_PAUSE"},
    )
    post(
        f"/tickets/{tid}/request-agent",
        own,
        {"expected_revision": 1, "message": "로컬 합성 문의 검증", "reason_code": "CUSTOMER_REQUEST"},
        "phase6-http-human",
    )
    # This existing test fixture calls real HANDOFF claim; no routing engine.
    from tests.http_scenario import assign_fixture, human_gate

    assign_fixture(factory, tid, stable_id("agent"))
    material_fixture(factory, tid, synthetic=True)
    result = request("POST", f"/staff/tickets/{tid}/internal", headers=agent, json=purpose)
    import json

    if result["material_status"] != "SYNTHETIC_ONLY" or "PRIVATE_" in json.dumps(result):
        raise RuntimeError("HTTP_INTERNAL_ALLOWLIST_FAILED")
    if result["current_proposals"][0]["approvals"][0]["usable_for_execution"] is not False:
        raise RuntimeError("HTTP_SYNTHETIC_APPROVAL_EXPOSED_AS_AUTHORITY")
    visible = request("POST", f"/staff/customers/{result['customer_ref']}/360", headers=agent, json=purpose)
    if visible["total_ticket_count"] != 1:
        raise RuntimeError("HTTP_INTERNAL_REF_EXPANDED_CUSTOMER_HISTORY")
    request("POST", f"/staff/tickets/{tid}/internal", headers=own, json=purpose, status=403)
    public = request("GET", f"/tickets/{tid}", headers=own)
    if "PRIVATE_" in json.dumps(public) or "current_proposals" in public:
        raise RuntimeError("HTTP_CUSTOMER_INTERNAL_LEAK")
    f = post(
        "/staff/followups",
        agent,
        {
            "ticket_id": tid,
            "owner_team_id": stable_id("team"),
            "owner_user_id": stable_id("agent"),
            "kind": "LOCAL_CHECK",
            "public_note": "로컬 공개 후속",
            "blocks_resolution": False,
        },
        "phase6-human-followup",
    )
    request(
        "POST",
        f"/staff/followups/{f['action_id']}/status",
        headers=agent,
        json={"expected_revision": 1, "status": "DONE"},
    )
    human_gate(factory, tid, stable_id("agent"), blocked=False)
    if request("GET", control, headers=admin)["paused"] is not True:
        raise RuntimeError("HTTP_HUMAN_PATH_CHANGED_PAUSE")
    request(
        "POST",
        control + "/resume",
        headers=admin,
        json={"expected_revision": 4, "stopped_revision": 4, "reason_code": "VERIFICATION_COMPLETE"},
    )
    history = request("GET", control + "/history", headers=admin)
    if [r["revision"] for r in history] != [5, 4, 3, 2, 1]:
        raise RuntimeError("HTTP_CONTROL_HISTORY_MISSING")
    with factory() as s:
        if s.scalar(select(func.count()).select_from(automation_rules).where(automation_rules.c.active)) != 0:
            raise RuntimeError("HTTP_RESUME_ACTIVATED_RULES")
    return [
        "explicit_queue_and_unrouted_capabilities",
        "queue_does_not_grant_internal_or_360",
        "staff_internal_nested_allowlist",
        "stop_blocks_claim_and_inflight_commit",
        "resume_fences_old_generation",
        "paused_handoff_human_followup_continue",
        "control_revision_and_history",
        "resume_does_not_activate_rules",
    ], {
        "phase6_internal_public_fields": sorted(result),
        "phase6_paused_generation": stopped["generation"],
        "phase6_control_history_revisions": [r["revision"] for r in history],
    }
