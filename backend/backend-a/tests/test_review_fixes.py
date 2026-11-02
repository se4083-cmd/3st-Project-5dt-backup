"""Independent-review reproductions. No real worker/model or external calls."""

import base64
import http.client
import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from queue import Queue
from time import sleep

import pytest
from sqlalchemy import event, select, text

from app import models as m
from app.analytics_canonical import digest
from app.config import Settings
from app.db import utcnow
from app.errors import APIError
from app.finalization import WorkRejected, commit_automatic_reply
from app.main import create_app
from app.model_constraints import team_categories, user_team_scopes
from app.repository import decode_cursor
from app.seed import stable_id
from app.staff_models import automation_control
from scripts import check_handoff_contract
from tests.conftest import ROOT, login_as
from tests.phase3_helpers import assign, staff_user
from tests.phase6_helpers import BASE, grant, route
from tests.test_finalization_contract import lease_reply, require_postgres, wait_for_blocker
from tests.test_flow import submit


def cursor(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


def final_state(factory, tid):
    """Only a digest leaves this test helper, never messages or audit payloads."""
    with factory() as s:
        return digest(
            {
                t.name: [dict(r) for r in s.execute(select(t).where(t.c.ticket_id == tid)).mappings()]
                for t in [m.tickets, m.automation_jobs, m.messages, m.audit_events]
            }
        )


@pytest.mark.parametrize(
    "change",
    [
        "scope_revoked",
        "category_changed",
        "category_removed",
        "agent_team_changed",
        "ticket_team_changed",
        "assignment_team_changed",
        "agent_disabled",
        "assignment_ended",
        "ticket_stage_changed",
    ],
)
def test_unusable_assignment_returns_to_scoped_queue_and_counts(client, headers, app, change):
    tid = submit(client, headers).json()["ticket_id"]
    assign(app, tid)
    route(app, tid)
    grant(app, "admin", "EXCEPTION_QUEUE_READ")
    admin, agent = login_as(client, "admin"), login_as(client, "agent")
    assert client.get(f"/api/v1/tickets/{tid}", headers=agent).status_code == 200
    assert client.get(BASE + "/exception-queue", headers=admin).json()["total"] == 0
    other = stable_id("review-other-team")
    if change in {"agent_team_changed", "ticket_team_changed", "assignment_team_changed"}:
        staff_user(app, "review-other-agent", team_id=other)
    with app.state.session_factory.begin() as s:
        if change == "scope_revoked":
            s.execute(
                user_team_scopes.delete().where(
                    user_team_scopes.c.user_id == stable_id("agent"),
                    user_team_scopes.c.team_id == stable_id("team"),
                )
            )
        elif change == "category_changed":
            s.execute(m.tickets.update().where(m.tickets.c.ticket_id == tid).values(category="PRODUCT"))
        elif change == "category_removed":
            s.execute(
                team_categories.delete().where(
                    team_categories.c.team_id == stable_id("team"), team_categories.c.category == "DELIVERY"
                )
            )
        elif change == "agent_team_changed":
            s.execute(m.users.update().where(m.users.c.user_id == stable_id("agent")).values(team_id=other))
        elif change == "ticket_team_changed":
            s.execute(m.tickets.update().where(m.tickets.c.ticket_id == tid).values(team_id=other))
        elif change == "assignment_team_changed":
            s.execute(m.assignments.update().where(m.assignments.c.ticket_id == tid).values(team_id=other))
        elif change == "agent_disabled":
            s.execute(m.users.update().where(m.users.c.user_id == stable_id("agent")).values(active=False))
        elif change == "assignment_ended":
            s.execute(
                m.assignments.update().where(m.assignments.c.ticket_id == tid).values(ended_at=utcnow())
            )
        else:
            s.execute(m.tickets.update().where(m.tickets.c.ticket_id == tid).values(status="OPEN"))
    assert client.get(f"/api/v1/tickets/{tid}", headers=agent).status_code == (
        401 if change == "agent_disabled" else 404
    )
    for params in [{}, {"reason": "UNASSIGNED"}, {"team_id": stable_id("team"), "limit": 1}]:
        page = client.get(BASE + "/exception-queue", headers=admin, params=params)
        counts = client.get(
            BASE + "/exception-queue/counts",
            headers=admin,
            params={k: v for k, v in params.items() if k != "limit"},
        )
        assert page.status_code == counts.status_code == 200
        assert page.json()["total"] == counts.json()["total"] == 1
        assert page.json()["counts"] == counts.json()["counts"] == {"UNASSIGNED": 1}
        assert [r["ticket_id"] for r in page.json()["items"]] == [tid]


def test_inactive_assignment_team_requires_explicit_quarantine_permission(client, headers, app):
    tid = submit(client, headers).json()["ticket_id"]
    assign(app, tid)
    route(app, tid)
    grant(app, "admin", "EXCEPTION_QUEUE_READ")
    with app.state.session_factory.begin() as s:
        s.execute(m.teams.update().where(m.teams.c.team_id == stable_id("team")).values(active=False))
    admin = login_as(client, "admin")
    assert client.get(f"/api/v1/tickets/{tid}", headers=login_as(client, "agent")).status_code == 404
    assert client.get(BASE + "/exception-queue", headers=admin).json()["total"] == 0
    assert (
        client.get(BASE + "/exception-queue", headers=admin, params={"queue_scope": "UNROUTED"}).status_code
        == 403
    )
    grant(app, "admin", "UNROUTED_QUEUE_READ")
    page = client.get(BASE + "/exception-queue", headers=admin, params={"queue_scope": "UNROUTED"}).json()
    counts = client.get(
        BASE + "/exception-queue/counts", headers=admin, params={"queue_scope": "UNROUTED"}
    ).json()
    assert page["total"] == counts["total"] == 1 and page["counts"] == counts["counts"]
    assert page["items"][0]["route_team_id"] is None


@pytest.mark.parametrize("value", [123, True, None, {}, [], 1.5])
@pytest.mark.parametrize("element", [0, 1])
def test_cursor_requires_two_string_elements(value, element):
    data = ["2026-10-01T00:00:00+00:00", stable_id("team")]
    data[element] = value
    with pytest.raises(APIError) as exc:
        decode_cursor(cursor(data))
    assert exc.value.status == 422 and exc.value.code == "INVALID_CURSOR"


@pytest.mark.parametrize(
    "endpoint",
    [
        "tickets",
        "orders",
        "messages",
        "public_followups",
        "staff_followups",
        "queue",
        "360_tickets",
        "360_followups",
    ],
)
def test_invalid_uuid_cursor_is_422_on_every_page_api(client, headers, app, endpoint):
    tid = submit(client, headers).json()["ticket_id"]
    assign(app, tid)
    grant(app, "admin", "EXCEPTION_QUEUE_READ")
    agent = login_as(client, "agent")
    routes = {
        "tickets": ("GET", "/api/v1/tickets", headers),
        "orders": ("GET", "/api/v1/orders", headers),
        "messages": ("GET", f"/api/v1/tickets/{tid}/messages", headers),
        "public_followups": ("GET", "/api/v1/followups", headers),
        "staff_followups": ("GET", BASE + "/followups", agent),
        "queue": ("GET", BASE + "/exception-queue", login_as(client, "admin")),
        "360_tickets": ("POST", BASE + f"/customers/{stable_id('customer1/profile')}/360/tickets", agent),
        "360_followups": ("POST", BASE + f"/customers/{stable_id('customer1/profile')}/360/followups", agent),
    }
    method, path, h = routes[endpoint]
    kwargs = {"json": {"purpose_code": "ACTIVE_SUPPORT"}} if method == "POST" else {}
    response = client.request(
        method, path, headers=h, params={"cursor": cursor(["2026-10-01T00:00:00+00:00", 123])}, **kwargs
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_CURSOR"


def test_control_select_delay_cannot_finalize_expired_lease(client, headers, app):
    tid = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, tid)
    f = app.state.session_factory
    with f.begin() as s:
        s.execute(
            m.automation_jobs.update()
            .where(m.automation_jobs.c.job_id == str(command.job_id))
            .values(lease_until=utcnow() + timedelta(seconds=0.4))
        )
    before = final_state(f, tid)
    waits = []

    def delay(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().startswith("SELECT") and "FROM automation_control" in statement:
            waits.append(True)
            sleep(0.6)

    event.listen(app.state.engine, "before_cursor_execute", delay)
    try:
        # Catch inside outer transaction: a rejection must leave no partial
        # final writes even when the caller commits that transaction.
        with f.begin() as s:
            with pytest.raises(WorkRejected, match="INVALID_LEASE"):
                commit_automatic_reply(s, command)
    finally:
        event.remove(app.state.engine, "before_cursor_execute", delay)
    assert waits == [True] and final_state(f, tid) == before


def test_success_timestamps_use_fresh_clock_after_control_gate(client, headers, app):
    tid = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, tid)
    after = []

    def delay(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().startswith("SELECT") and "FROM automation_control" in statement:
            sleep(0.1)

    def gate_returned(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().startswith("SELECT") and "FROM automation_control" in statement:
            after.append(utcnow())

    event.listen(app.state.engine, "before_cursor_execute", delay)
    event.listen(app.state.engine, "after_cursor_execute", gate_returned)
    try:
        with app.state.session_factory.begin() as s:
            commit_automatic_reply(s, command)
    finally:
        event.remove(app.state.engine, "before_cursor_execute", delay)
        event.remove(app.state.engine, "after_cursor_execute", gate_returned)
    with app.state.session_factory() as s:
        msg = (
            s.execute(select(m.messages).where(m.messages.c.ticket_id == tid, m.messages.c.final_reply))
            .mappings()
            .one()
        )
        ticket = s.execute(select(m.tickets).where(m.tickets.c.ticket_id == tid)).mappings().one()
        job = (
            s.execute(select(m.automation_jobs).where(m.automation_jobs.c.job_id == str(command.job_id)))
            .mappings()
            .one()
        )
        assert after and msg["created_at"] >= after[0]
        assert (
            ticket["resolved_at"]
            == ticket["first_replied_at"]
            == ticket["updated_at"]
            == job["updated_at"]
            == msg["created_at"]
        )


@pytest.mark.postgres
def test_postgres_control_lock_wait_expires_lease_without_partial_writes(client, headers, app):
    require_postgres(app)
    tid = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, tid)
    f = app.state.session_factory
    expires = utcnow() + timedelta(seconds=2)
    with f.begin() as s:
        s.execute(
            m.automation_jobs.update()
            .where(m.automation_jobs.c.job_id == str(command.job_id))
            .values(lease_until=expires)
        )
    before = final_state(f, tid)
    pids = Queue()

    def commit():
        with f.begin() as s:
            pids.put(s.scalar(text("SELECT pg_backend_pid()")))
            try:
                commit_automatic_reply(s, command)
            except WorkRejected as exc:
                return exc.code
        return "UNEXPECTED_SUCCESS"

    with ThreadPoolExecutor(max_workers=1) as pool:
        with f.begin() as locker:
            locker.execute(select(automation_control).with_for_update()).one()
            future = pool.submit(commit)
            wait_for_blocker(app, pids.get(timeout=5))
            sleep(max(0, (expires - utcnow()).total_seconds()) + 0.1)
        assert future.result(timeout=10) == "INVALID_LEASE"
    assert final_state(f, tid) == before


def test_openapi_fixed_phrases_survive_python312_http_defaults(monkeypatch):
    monkeypatch.setitem(http.client.responses, 413, "Request Entity Too Large")
    monkeypatch.setitem(http.client.responses, 422, "Unprocessable Entity")
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret=secrets.token_urlsafe(48),
        )
    )
    try:
        assert app.openapi() == json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    finally:
        app.state.engine.dispose()


@pytest.mark.parametrize("difference", ["field", "security", "response", "description"])
def test_contract_checker_does_not_ignore_real_differences(tmp_path, monkeypatch, difference):
    contract = deepcopy(json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8")))
    if difference == "field":
        contract["components"]["schemas"]["TicketPublic"]["properties"].pop("revision")
    elif difference == "security":
        contract["paths"]["/api/v1/tickets"]["get"]["security"] = []
    elif difference == "response":
        contract["paths"]["/api/v1/tickets"]["get"]["responses"].pop("422")
    else:
        contract["paths"]["/api/v1/tickets"]["get"]["responses"]["413"]["description"] = (
            "unexpected description"
        )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/openapi.json").write_text(json.dumps(contract), encoding="utf-8")
    monkeypatch.setattr(check_handoff_contract, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["check_handoff_contract"])
    with pytest.raises(RuntimeError, match="OPENAPI_NEEDS_REGENERATION"):
        check_handoff_contract.main()
