"""Review-fix HTTP regression; DB calls remain explicit synthetic test boundaries."""

from datetime import timedelta
from time import sleep

from sqlalchemy import event

from app.db import utcnow
from app.finalization import AutomaticReply, WorkRejected, commit_automatic_reply
from app.jobs import claim_jobs
from app.model_constraints import user_team_scopes
from app.models import automation_jobs, tickets
from app.seed import stable_id
from tests.test_review_fixes import cursor, final_state


def run_review_fixes(factory, request, post, login, own, admin):
    from tests.http_scenario import assign_fixture, clone_staff

    uid = clone_staff(factory, "review-agent", "agent", "AGENT", [stable_id("team")])
    agent = login("review-agent")
    tid = post(
        "/tickets",
        own,
        {"order_id": stable_id("customer1/order/0"), "message": "로컬 검토 회귀용 합성 문의"},
        "http-review-assignment",
    )["ticket_id"]
    with factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(category="DELIVERY"))
    post(
        f"/tickets/{tid}/request-agent",
        own,
        {"expected_revision": 1, "reason_code": "CUSTOMER_REQUEST", "message": "로컬 합성 사람 연결"},
        "http-review-agent",
    )
    assign_fixture(factory, tid, uid)
    request("GET", f"/tickets/{tid}", headers=agent)

    bad = cursor(["2026-10-01T00:00:00+00:00", 123])
    paths = [
        ("GET", "/tickets", own),
        ("GET", "/orders", own),
        ("GET", f"/tickets/{tid}/messages", own),
        ("GET", "/followups", own),
        ("GET", "/staff/followups", agent),
        ("GET", "/staff/exception-queue", admin),
        ("POST", f"/staff/customers/{stable_id('customer1/profile')}/360/tickets", agent),
        ("POST", f"/staff/customers/{stable_id('customer1/profile')}/360/followups", agent),
    ]
    for method, path, headers in paths:
        kwargs = {"json": {"purpose_code": "ACTIVE_SUPPORT"}} if method == "POST" else {}
        result = request(method, path, headers=headers, params={"cursor": bad}, status=422, **kwargs)
        if result["error"]["code"] != "INVALID_CURSOR":
            raise RuntimeError("HTTP_INVALID_CURSOR_CONTRACT")

    before = request("GET", "/staff/exception-queue", headers=admin)["total"]
    with factory.begin() as s:
        s.execute(
            user_team_scopes.delete().where(
                user_team_scopes.c.user_id == uid, user_team_scopes.c.team_id == stable_id("team")
            )
        )
    request("GET", f"/tickets/{tid}", headers=agent, status=404)
    page = request("GET", "/staff/exception-queue", headers=admin)
    counts = request("GET", "/staff/exception-queue/counts", headers=admin)
    if (
        page["total"] != before + 1
        or page["total"] != counts["total"]
        or page["counts"] != counts["counts"]
        or tid not in [i["ticket_id"] for i in page["items"]]
    ):
        raise RuntimeError("HTTP_REVOKED_ASSIGNMENT_HIDDEN_FROM_QUEUE")

    auto = post("/tickets", own, {"message": "로컬 만료 lease 회귀용 합성 문의"}, "http-review-expiry")[
        "ticket_id"
    ]
    with factory.begin() as s:
        job = next(j for j in claim_jobs(s, "http-review-expiry", limit=100) if j["ticket_id"] == auto)
        s.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == job["job_id"])
            .values(lease_until=utcnow() + timedelta(seconds=0.4))
        )
    command = AutomaticReply(
        job_id=job["job_id"],
        cycle_no=job["cycle_no"],
        expected_revision=job["expected_ticket_version"],
        lease_token=job["lease_token"],
        worker_id="http-review-expiry",
        automation_generation=job["automation_generation"],
        message="저장되면 안 되는 고정 합성 답변",
    )
    previous = final_state(factory, auto)
    engine = factory.kw["bind"]

    def delay(conn, cur, statement, parameters, context, many):
        if statement.lstrip().startswith("SELECT") and "FROM automation_control" in statement:
            sleep(0.6)

    event.listen(engine, "before_cursor_execute", delay)
    rejected = False
    try:
        with factory.begin() as s:
            try:
                commit_automatic_reply(s, command)
            except WorkRejected as exc:
                if exc.code != "INVALID_LEASE":
                    raise
                rejected = True
    finally:
        event.remove(engine, "before_cursor_execute", delay)
    if not rejected or final_state(factory, auto) != previous:
        raise RuntimeError("HTTP_EXPIRED_LEASE_PARTIAL_FINAL_WRITE")
    detail = request("GET", f"/tickets/{auto}", headers=own)
    if detail["stage"] != "RECEIVED" or len(detail["messages"]) != 1:
        raise RuntimeError("HTTP_EXPIRED_LEASE_RESPONSE_VISIBLE")
    return [
        "review_invalid_cursor_422_across_eight_http_pages",
        "review_revoked_assignment_visible_in_scoped_queue",
        "review_delayed_expired_lease_has_no_partial_final_writes",
    ], {"review_cursor_pages": len(paths), "review_lease_rejection": "INVALID_LEASE"}
