import pytest
from sqlalchemy import func, select

from app import audit
from app.finalization import WorkRejected, commit_automatic_reply
from app.models import automation_jobs
from app.staff_models import automation_control, automation_control_history
from tests.conftest import login_as
from tests.phase6_helpers import BASE, grant, route
from tests.test_finalization_contract import lease_reply
from tests.test_flow import submit


def stop(client, h, revision=1):
    return client.post(
        BASE + "/automation-control/stop",
        headers=h,
        json={"expected_revision": revision, "reason_code": "SAFETY_INCIDENT"},
    )


def resume(client, h, revision=2, stopped_revision=2):
    return client.post(
        BASE + "/automation-control/resume",
        headers=h,
        json={
            "expected_revision": revision,
            "stopped_revision": stopped_revision,
            "reason_code": "INCIDENT_RESOLVED",
        },
    )


@pytest.mark.parametrize("role", ["customer1", "agent", "admin"])
def test_control_has_no_implicit_role_permission(client, app, role):
    h = login_as(client, role)
    assert client.get(BASE + "/automation-control", headers=h).status_code == 403
    assert stop(client, h).status_code == 403
    assert resume(client, h).status_code == 403


@pytest.mark.parametrize("role", ["customer1", "agent"])
def test_admin_control_capabilities_do_not_override_role(client, app, role):
    grant(app, role, "AUTOMATION_READ", "AUTOMATION_STOP", "AUTOMATION_RESUME")
    h = login_as(client, role)
    assert client.get(BASE + "/automation-control", headers=h).status_code == 403
    assert stop(client, h).status_code == 403 and resume(client, h).status_code == 403
    if role == "agent":
        assert client.get(BASE + "/capabilities", headers=h).json()["capabilities"] == []


def test_distinct_stop_resume_permissions_history_and_conflicts(client, app):
    grant(app, "admin", "AUTOMATION_READ", "AUTOMATION_STOP")
    h = login_as(client, "admin")
    assert stop(client, h).json()["generation"] == 2
    assert stop(client, h).status_code == 409
    assert resume(client, h).status_code == 403
    grant(app, "admin", "AUTOMATION_RESUME")
    assert resume(client, h, stopped_revision=1).status_code == 409
    assert resume(client, h).json()["generation"] == 3
    assert resume(client, h).status_code == 409
    history = client.get(BASE + "/automation-control/history", headers=h).json()
    assert [r["revision"] for r in history] == [3, 2, 1] and [r["paused"] for r in history] == [
        False,
        True,
        False,
    ]


def test_inflight_is_blocked_and_not_revived_after_resume(client, headers, app):
    tid = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, tid)
    grant(app, "admin", "AUTOMATION_READ", "AUTOMATION_STOP", "AUTOMATION_RESUME", "EXCEPTION_QUEUE_READ")
    route(app, tid)
    h = login_as(client, "admin")
    assert stop(client, h).status_code == 200
    with pytest.raises(WorkRejected, match="AUTOMATION_PAUSED"), app.state.session_factory.begin() as s:
        commit_automatic_reply(s, command)
    q = client.get(BASE + "/exception-queue", headers=h).json()
    assert q["items"][0]["automatic_state"] == "PAUSED" and q["items"][0]["job_state"] == "RUNNING"
    assert resume(client, h).status_code == 200
    with (
        pytest.raises(WorkRejected, match="AUTOMATION_GENERATION_CHANGED"),
        app.state.session_factory.begin() as s,
    ):
        commit_automatic_reply(s, command)
    with app.state.session_factory() as s:
        assert (
            s.scalar(select(automation_jobs.c.status).where(automation_jobs.c.ticket_id == tid)) == "RUNNING"
        )


@pytest.mark.parametrize("operation", ["stop", "resume"])
def test_control_audit_failure_rolls_back_state_and_history(client, app, monkeypatch, operation):
    grant(app, "admin", "AUTOMATION_READ", "AUTOMATION_STOP", "AUTOMATION_RESUME")
    h = login_as(client, "admin")
    if operation == "resume":
        assert stop(client, h).status_code == 200
    before = client.get(BASE + "/automation-control", headers=h).json()
    original = audit.record

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        if args[2] in {"AUTOMATION_STOPPED", "AUTOMATION_RESUMED"}:
            raise RuntimeError("injected")

    monkeypatch.setattr(audit, "record", fail)
    r = stop(client, h) if operation == "stop" else resume(client, h)
    assert r.status_code == 500
    assert client.get(BASE + "/automation-control", headers=h).json() == before
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(automation_control_history)) == before["revision"]


def test_missing_control_fails_closed_but_customer_and_handoff_remain(client, headers, app):
    tid = submit(client, headers).json()["ticket_id"]
    command = lease_reply(app, tid)
    with app.state.session_factory.begin() as s:
        s.execute(automation_control.delete())
    with (
        pytest.raises(WorkRejected, match="AUTOMATION_CONTROL_UNAVAILABLE"),
        app.state.session_factory.begin() as s,
    ):
        commit_automatic_reply(s, command)
    assert (
        client.post(
            f"/api/v1/tickets/{tid}/request-agent",
            headers={**headers, "Idempotency-Key": "missing-control-human"},
            json={"expected_revision": 1, "message": "합성 사람 요청", "reason_code": "CUSTOMER_REQUEST"},
        ).status_code
        == 201
    )
    grant(app, "admin", "AUTOMATION_READ")
    assert client.get(BASE + "/automation-control", headers=login_as(client, "admin")).status_code == 503
