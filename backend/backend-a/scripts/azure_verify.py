"""Real HTTPS acceptance against the dedicated A development deployment.

Only newly created synthetic tickets are changed by test-only DB writers.
Those writers are NOT a Backend B engine and are NOT exposed through HTTP.
No remote pytest suite, model, RAG, Fabric, message sending or deletion runs.
"""

import argparse
import ipaddress
import json
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select, text

from app import audit, repository
from app.config import Settings
from app.db import build_engine, session_factory, utcnow
from app.exception_queue import RouteCommand, record_queue_route
from app.jobs import claim_jobs
from app.model_constraints import team_categories
from app.models import assignments, automation_jobs, messages, teams, tickets
from app.resolution import WorkRejected, lock_resolution_gate
from app.schema import metadata
from app.seed import stable_id
from app.staff_models import automation_control
from scripts.azure_bootstrap import cloud_id
from scripts.azure_deploy import (
    APP,
    BASE,
    GROUP,
    PG,
    ROOT,
    SUBSCRIPTION,
    az,
    close_operator_firewall,
    database_url,
    owned,
    rest,
    state,
)


def expect(condition, code):
    if not condition:
        raise RuntimeError(code)


@contextmanager
def operator_access(directory):
    pg_id = BASE + f"Microsoft.DBforPostgreSQL/flexibleServers/{PG}"
    owned(rest(directory, "get", pg_id, "2024-08-01"))
    events = az(
        "monitor",
        "activity-log",
        "list",
        "--resource-id",
        BASE + f"Microsoft.Web/sites/{APP}",
        "--offset",
        "6h",
        "--max-events",
        "100",
        "--subscription",
        SUBSCRIPTION,
    )
    ip = next(
        (
            (e.get("httpRequest") or {}).get("clientIpAddress")
            for e in events
            if (e.get("httpRequest") or {}).get("clientIpAddress")
        ),
        None,
    )
    expect(bool(ip), "OPERATOR_IP_UNAVAILABLE")
    ip = str(ipaddress.IPv4Address(ip))
    rule = pg_id + "/firewallRules/backend-a-verification-temporary"
    rest(directory, "put", rule, "2024-08-01", {"properties": {"startIpAddress": ip, "endIpAddress": ip}})
    engine = None
    try:
        values = state(directory)
        engine = build_engine(
            Settings(
                _env_file=None,
                app_env="production",
                jwt_secret=values["jwt"],
                database_url=database_url(values, local=True),
            )
        )
        yield session_factory(engine)
    finally:
        if engine:
            engine.dispose()
        close_operator_firewall(directory, rule)


def assignment_fixture(factory, tid):
    """Fixed synthetic assignment ONLY to this run's known new ticket."""
    with factory.begin() as session:
        ticket = (
            session.execute(select(tickets).where(tickets.c.ticket_id == tid).with_for_update())
            .mappings()
            .one()
        )
        expect(ticket["customer_id"] == cloud_id("customer1/profile"), "FIXTURE_CUSTOMER_MISMATCH")
        job = (
            session.execute(
                select(automation_jobs)
                .where(
                    automation_jobs.c.ticket_id == tid,
                    automation_jobs.c.cycle_no == ticket["cycle_no"],
                    automation_jobs.c.job_kind == "HANDOFF",
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        expect(job["status"] == "PENDING", "FIXTURE_HANDOFF_NOT_PENDING")
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
                agent_id=cloud_id("agent"),
                # Use the deployment DB clock, not a developer PC clock which
                # may be ahead of App Service. Do not bypass future-assignment checks.
                assigned_at=session.scalar(text("SELECT clock_timestamp()")),
                reason_code="AZURE_SYNTHETIC_TEST_ONLY",
            )
        )
        session.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == job["job_id"])
            .values(status="HANDED_OFF", lease_token=None, lease_owner=None, lease_until=None)
        )
        audit.record(session, None, "SYNTHETIC_ASSIGNMENT_FIXTURE", "TICKET", tid, service="azure-acceptance")


def resolution_fixture(factory, tid, *, blocked):
    try:
        with factory.begin() as session:
            ticket = session.execute(select(tickets).where(tickets.c.ticket_id == tid)).mappings().one()
            user = repository.get_user(session, cloud_id("agent"))
            ticket = lock_resolution_gate(
                session,
                tid,
                expected_revision=ticket["version"],
                cycle_no=ticket["cycle_no"],
                mode="HUMAN",
                human_user=user,
            )
            expect(not blocked, "MANDATORY_FOLLOWUP_DID_NOT_BLOCK")
            session.execute(
                messages.insert().values(
                    message_id=str(uuid4()),
                    ticket_id=tid,
                    cycle_no=ticket["cycle_no"],
                    role="AGENT",
                    direction="OUT",
                    visibility="PUBLIC",
                    final_reply=True,
                    body="Synthetic fixed response; not a Backend B or AI result.",
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
                session,
                cloud_id("agent"),
                "SYNTHETIC_EXPLICIT_RESOLUTION",
                "TICKET",
                tid,
                service="azure-acceptance",
            )
    except WorkRejected as exc:
        expect(blocked and exc.code == "BLOCKING_FOLLOWUP", "UNEXPECTED_RESOLUTION_GATE_REJECTION")


def business_fingerprint(factory):
    result = {}
    with factory() as session:
        for name in sorted(set(metadata.tables) - {"audit_events"}):
            # Fixed model allowlist only; return hashes, never row data/notes.
            row = session.execute(
                text(f'''SELECT count(*), md5(coalesce(string_agg(h, '' ORDER BY h), ''))
                 FROM (SELECT md5(row_to_json(t)::text) AS h FROM "{name}" t) rows''')
            ).one()
            result[name] = tuple(row)
    return result


def verify(directory):
    values = state(directory)
    resources = json.loads((directory / "resources.json").read_text())
    checks = []
    request_count = 0
    with (
        operator_access(directory) as factory,
        httpx.Client(
            base_url=resources["api_url"], trust_env=False, timeout=60, follow_redirects=False
        ) as client,
    ):

        def request(method, path, *, status=200, **kwargs):
            nonlocal request_count
            response = client.request(method, path, **kwargs)
            request_count += 1
            expect(
                response.status_code == status,
                "HTTPS_STATUS_MISMATCH_" + str(status) + "_GOT_" + str(response.status_code),
            )
            return response

        request("GET", "/health/live")
        request("GET", "/health/ready")
        expect(
            request("GET", "/docs").headers.get("Strict-Transport-Security") == "max-age=31536000",
            "HSTS_MISSING",
        )
        spec = request("GET", "/openapi.json").json()
        expect(
            spec == json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8")), "OPENAPI_MISMATCH"
        )
        expect(
            not any(
                "retention" in p and any(m in spec["paths"][p] for m in ("delete", "put"))
                for p in spec["paths"]
            ),
            "RETENTION_DELETE_ROUTE",
        )
        with factory() as session:
            expect(
                session.scalar(text("SELECT version_num FROM alembic_version")) == "0006",
                "MIGRATION_MISMATCH",
            )
            expect(
                session.scalar(text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")),
                "DATABASE_TLS_MISSING",
            )
        checks += ["https_live_ready_migration0006_tls", "swagger_openapi_and_no_retention_delete"]
        request("GET", "/api/v1/orders", status=401)
        request(
            "POST",
            "/api/v1/auth/login",
            status=401,
            json={
                "login_name": "demo-customer1@csflow.example.test",
                "password": "incorrect-synthetic-input",
            },
        )
        request(
            "POST",
            "/api/v1/auth/login",
            status=401,
            json={"login_name": "dev-customer1@example.test", "password": "incorrect-synthetic-input"},
        )
        headers = {}
        for label in ("customer1", "customer2", "agent", "admin"):
            response = request(
                "POST",
                "/api/v1/auth/login",
                json={
                    "login_name": f"demo-{label}@csflow.example.test",
                    "password": values["accounts"][label],
                },
            )
            headers[label] = {"Authorization": "Bearer " + response.json()["access_token"]}
        own, other, agent, admin = (headers[k] for k in ("customer1", "customer2", "agent", "admin"))
        checks.append("four_roles_login_invalid_and_anonymous_denied")
        order = request("GET", "/api/v1/orders", headers=own).json()["items"][0]["order_id"]
        request("GET", f"/api/v1/orders/{order}", headers=other, status=404)
        key = "azure-acceptance-" + uuid4().hex
        body = {"order_id": order, "message": "Synthetic Azure acceptance inquiry, no external action."}
        tid = request(
            "POST", "/api/v1/tickets", headers={**own, "Idempotency-Key": key}, json=body, status=201
        ).json()["ticket_id"]
        replay = request("POST", "/api/v1/tickets", headers={**own, "Idempotency-Key": key}, json=body).json()
        expect(replay["ticket_id"] == tid, "IDEMPOTENT_REPLAY_MISMATCH")
        request(
            "POST",
            "/api/v1/tickets",
            headers={**own, "Idempotency-Key": key},
            json={**body, "message": "Different synthetic payload"},
            status=409,
        )
        request("GET", f"/api/v1/tickets/{tid}", headers=other, status=404)
        request(
            "POST",
            f"/api/v1/staff/tickets/{tid}/internal",
            headers=agent,
            json={"purpose_code": "ACTIVE_SUPPORT"},
            status=404,
        )
        checks += [
            "orders_ticket_ownership",
            "ticket_create_idempotent_retry_and_conflict",
            "unassigned_staff_internal_denied",
        ]
        t = request("GET", f"/api/v1/tickets/{tid}", headers=own).json()
        reopened = request(
            "POST",
            f"/api/v1/tickets/{tid}/reopen",
            status=201,
            headers={**own, "Idempotency-Key": key + "-reopen"},
            json={"expected_revision": t["revision"], "message": "Synthetic re-inquiry"},
        ).json()
        request(
            "POST",
            f"/api/v1/tickets/{tid}/reopen",
            headers={**own, "Idempotency-Key": key + "-stale"},
            json={"expected_revision": t["revision"], "message": "Stale synthetic request"},
            status=409,
        )
        human = request(
            "POST",
            f"/api/v1/tickets/{tid}/request-agent",
            status=201,
            headers={**own, "Idempotency-Key": key + "-human"},
            json={
                "expected_revision": reopened["revision"],
                "message": "Synthetic human request",
                "reason_code": "CUSTOMER_REQUEST",
            },
        ).json()
        expect(human["handling_mode"] == "HUMAN", "HUMAN_MODE_MISSING")
        checks.append("reopen_revision_conflict_and_human_request")
        with factory.begin() as session:
            record_queue_route(
                session,
                tid,
                RouteCommand(
                    expected_revision=human["revision"],
                    cycle_no=human["cycle_no"],
                    expected_route_revision=0,
                    team_id=stable_id("team"),
                ),
                service_id="azure-synthetic-fixture",
            )
        queue = request("GET", "/api/v1/staff/exception-queue", headers=admin).json()
        expect(any(str(x["ticket_id"]) == tid for x in queue["items"]), "ROUTED_QUEUE_MISSING")
        counts = request("GET", "/api/v1/staff/exception-queue/counts", headers=admin).json()
        expect(counts["total"] == queue["total"], "QUEUE_COUNTS_MISMATCH")
        request("GET", "/api/v1/staff/exception-queue?queue_scope=UNROUTED", headers=admin, status=403)
        request(
            "POST",
            f"/api/v1/staff/tickets/{tid}/internal",
            headers=agent,
            json={"purpose_code": "ACTIVE_SUPPORT"},
            status=404,
        )
        checks.append("routed_queue_minimum_scope_and_no_access_expansion")
        assignment_fixture(factory, tid)
        detail = request(
            "POST",
            f"/api/v1/staff/tickets/{tid}/internal",
            headers=agent,
            json={"purpose_code": "ACTIVE_SUPPORT"},
        ).json()
        expect(detail["material_status"] == "MISSING", "FABRICATED_AI_MATERIAL")
        request(
            "POST",
            f"/api/v1/staff/tickets/{tid}/internal",
            headers=own,
            json={"purpose_code": "ACTIVE_SUPPORT"},
            status=403,
        )
        customer_path = f"/api/v1/staff/customers/{cloud_id('customer1/profile')}/360"
        baseline360 = request(
            "POST", customer_path, headers=admin, json={"purpose_code": "QUALITY_REVIEW"}
        ).json()
        with factory.begin() as session:
            hidden_team, hidden_tid = str(uuid4()), str(uuid4())
            team = dict(
                session.execute(select(teams).where(teams.c.team_id == stable_id("team"))).mappings().one()
            )
            team.update(team_id=hidden_team, name="Synthetic ungranted team " + hidden_team[:8])
            session.execute(teams.insert().values(**team))
            session.execute(team_categories.insert().values(team_id=hidden_team, category="DELIVERY"))
            hidden = dict(session.execute(select(tickets).where(tickets.c.ticket_id == tid)).mappings().one())
            hidden.update(
                ticket_id=hidden_tid,
                team_id=hidden_team,
                cycle_no=1,
                version=1,
                status="HANDOFF_PENDING",
                scenario_id="AZURE_ACCEPTANCE_SYNTHETIC",
                data_origin="SYNTHETIC",
            )
            session.execute(tickets.insert().values(**hidden))
            record_queue_route(
                session,
                hidden_tid,
                RouteCommand(expected_revision=1, cycle_no=1, expected_route_revision=0, team_id=hidden_team),
                service_id="azure-synthetic-fixture",
            )
        request(
            "POST",
            f"/api/v1/staff/tickets/{hidden_tid}/internal",
            headers=admin,
            json={"purpose_code": "QUALITY_REVIEW"},
            status=404,
        )
        request("GET", f"/api/v1/tickets/{hidden_tid}", headers=agent, status=404)
        scoped360 = request(
            "POST", customer_path, headers=admin, json={"purpose_code": "QUALITY_REVIEW"}
        ).json()
        expect(
            scoped360["total_ticket_count"] == baseline360["total_ticket_count"]
            and hidden_tid not in {str(x["ticket_id"]) for x in scoped360["recent_tickets"]},
            "CUSTOMER360_TEAM_LEAK",
        )
        scoped_queue = request("GET", "/api/v1/staff/exception-queue", headers=admin).json()
        expect(hidden_tid not in {str(x["ticket_id"]) for x in scoped_queue["items"]}, "QUEUE_TEAM_LEAK")
        request("GET", "/api/v1/admin/analytics/voc/top?team_ids=" + hidden_team, headers=admin, status=403)
        checks.append("cross_team_internal_queue_customer360_aggregate_scope")
        action = request(
            "POST",
            "/api/v1/staff/followups",
            headers={**agent, "Idempotency-Key": key + "-followup"},
            status=201,
            json={
                "ticket_id": tid,
                "owner_team_id": stable_id("team"),
                "owner_user_id": cloud_id("agent"),
                "kind": "SYNTHETIC_CHECK",
                "public_note": "Synthetic public followup",
                "internal_note": "AZURE_PRIVATE_FOLLOWUP_SENTINEL",
                "blocks_resolution": True,
            },
        ).json()
        fid = action["action_id"]
        public = request("GET", f"/api/v1/followups/{fid}", headers=own)
        expect(
            "internal_note" not in public.json() and "AZURE_PRIVATE_FOLLOWUP_SENTINEL" not in public.text,
            "INTERNAL_NOTE_LEAK",
        )
        resolution_fixture(factory, tid, blocked=True)
        request(
            "POST",
            f"/api/v1/staff/followups/{fid}/status",
            headers=agent,
            json={"expected_revision": 1, "status": "DONE"},
        )
        before = request("GET", f"/api/v1/tickets/{tid}", headers=own).json()
        expect(before["stage"] != "COMPLETED", "FOLLOWUP_AUTO_RESOLVED_TICKET")
        resolution_fixture(factory, tid, blocked=False)
        expect(
            request("GET", f"/api/v1/tickets/{tid}", headers=own).json()["stage"] == "COMPLETED",
            "EXPLICIT_RESOLUTION_MISSING",
        )
        checks += [
            "fixed_assignment_staff_internal_missing_material",
            "followup_public_private_separation",
            "common_human_gate_blocks_then_explicit_test_resolution",
        ]
        control = request("GET", "/api/v1/staff/automation-control", headers=admin).json()
        expect(control["paused"], "AUTOMATION_NOT_PAUSED")
        with factory.begin() as session:
            expect(
                claim_jobs(session, "azure-synthetic-paused-check", job_kind="AUTO") == [],
                "PAUSED_AUTO_CLAIM_ALLOWED",
            )
        request("GET", "/api/v1/staff/automation-control", headers=agent, status=403)
        request(
            "POST",
            "/api/v1/staff/automation-control/resume",
            headers=admin,
            status=403,
            json={
                "expected_revision": control["revision"],
                "stopped_revision": control["revision"],
                "reason_code": "VERIFICATION_COMPLETE",
            },
        )
        request(
            "POST",
            "/api/v1/staff/automation-control/stop",
            headers=admin,
            status=409,
            json={"expected_revision": control["revision"] - 1, "reason_code": "OPERATOR_PAUSE"},
        )
        checks.append("persistent_pause_explicit_control_and_revision_denial")
        before = business_fingerprint(factory)
        with factory() as session:
            preview_as_of = (
                session.scalar(text("SELECT clock_timestamp()")) - timedelta(seconds=2)
            ).isoformat()
        report = request(
            "POST",
            "/api/v1/staff/retention/dry-run",
            headers=admin,
            json={"purpose_code": "RETENTION_REVIEW", "as_of": preview_as_of},
        ).json()
        expect(report["dry_run"] and not report["business_data_modified"], "RETENTION_NOT_PREVIEW")
        expect(before == business_fingerprint(factory), "RETENTION_BUSINESS_DATA_CHANGED")
        request(
            "POST",
            "/api/v1/staff/retention/dry-run",
            headers=admin,
            status=403,
            json={"purpose_code": "RETENTION_REVIEW", "as_of": preview_as_of, "scope": "GLOBAL"},
        )
        checks.append("retention_team_preview_audit_no_business_change_global_denied")
        analytics = request("GET", "/api/v1/admin/analytics/voc/top", headers=admin).json()
        expect(
            analytics["availability"] == "UNAVAILABLE"
            and analytics["reason"] == "NO_PUBLISHED_BATCH"
            and analytics["meta"] is None,
            "ANALYTICS_NOT_PUBLISHED_CONTRACT",
        )
        request("GET", "/api/v1/admin/analytics/voc/top", headers=own, status=403)
        request("GET", "/api/v1/admin/analytics/kpi", headers=admin)
        checks.append("analytics_unpublished_customer_denied_no_fabric_call")
        # Deliberately test public process-local brute-force throttling with a
        # nonexistent synthetic identity, never locking a person's real account.
        for _ in range(10):
            request(
                "POST",
                "/api/v1/auth/login",
                status=401,
                json={
                    "login_name": "rate-limit-synthetic@example.test",
                    "password": "incorrect-synthetic-input",
                },
            )
        request(
            "POST",
            "/api/v1/auth/login",
            status=429,
            json={"login_name": "rate-limit-synthetic@example.test", "password": "incorrect-synthetic-input"},
        )
        checks.append("public_login_throttling")
        request("POST", "/api/v1/auth/login", content=b" " * 131073, status=413)
        checks.append("public_request_body_limit")
        with factory() as session:
            saved_control = dict(session.execute(select(automation_control)).mappings().one())
        az("webapp", "restart", "-g", GROUP, "-n", APP, "--subscription", SUBSCRIPTION)
        for _ in range(90):
            try:
                if client.get("/health/ready").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(5)
        else:
            raise RuntimeError("RESTART_READINESS_TIMEOUT")
        expect(
            request("GET", f"/api/v1/tickets/{tid}", headers=own).json()["stage"] == "COMPLETED",
            "DATA_NOT_PERSISTED",
        )
        with factory() as session:
            expect(
                dict(session.execute(select(automation_control)).mappings().one()) == saved_control,
                "PAUSE_NOT_PERSISTED",
            )
        checks.append("app_restart_data_and_pause_preserved")
    result = {
        "result": "PASS",
        "transport": "real public HTTPS",
        "database": "Azure PostgreSQL16 dedicated backend_a",
        "checks": checks,
        "check_groups": len(checks),
        "asserted_http_requests": request_count,
        "migration": "0006",
        "data_source": "SYNTHETIC",
        "actual_B_AI_Fabric_integration": False,
        "temporary_operator_firewall_closed": True,
        "completed_at": utcnow().isoformat(),
    }
    (directory / "https-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".cache/azure-backend-a")
    verify(parser.parse_args().state_dir.resolve())
