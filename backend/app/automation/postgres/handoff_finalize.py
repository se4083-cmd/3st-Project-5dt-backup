"""Atomically finalize a leased HANDOFF job."""

from uuid import UUID

from sqlalchemy import and_, select, update

from app.db import utcnow
from app.exception_queue import RouteCommand, record_queue_route
from app.models import automation_jobs, tickets, users
from app.staff_models import queue_routes

from .assignment import AssignmentRejected, assign_handoff_ticket


def finalize_handoff_job(
    session_factory,
    job: dict,
    worker_id: str,
    agent_id: str,
):
    """Route, assign and complete one HANDOFF job in one transaction."""

    if not worker_id or not worker_id.strip():
        raise ValueError("INVALID_WORKER_ID")

    if not agent_id:
        raise ValueError("INVALID_AGENT_ID")

    with session_factory.begin() as session:
        ticket = (
            session.execute(
                select(tickets)
                .where(tickets.c.ticket_id == job["ticket_id"])
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

        if ticket is None:
            raise AssignmentRejected("TICKET_NOT_FOUND")

        current_job = (
            session.execute(
                select(automation_jobs)
                .where(automation_jobs.c.job_id == job["job_id"])
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

        now = utcnow()

        if (
            current_job is None
            or current_job["ticket_id"] != ticket["ticket_id"]
            or current_job["job_kind"] != "HANDOFF"
            or current_job["status"] != "RUNNING"
            or current_job["lease_token"] != job["lease_token"]
            or current_job["lease_owner"] != worker_id
            or current_job["lease_until"] is None
            or current_job["lease_until"] <= now
        ):
            raise AssignmentRejected("HANDOFF_LEASE_INVALID")

        if (
            ticket["cycle_no"] != current_job["cycle_no"]
            or ticket["version"] != current_job["expected_ticket_version"]
            or ticket["status"] != "HANDOFF_PENDING"
            or ticket["requested_mode"] != "HUMAN"
        ):
            raise AssignmentRejected("HANDOFF_CONTEXT_CHANGED")


        agent = (
            session.execute(
                select(users)
                .where(users.c.user_id == agent_id)
            )
            .mappings()
            .one_or_none()
        )

        if (
            agent is None
            or not agent["active"]
            or agent["role"] != "AGENT"
            or agent["team_id"] is None
        ):
            raise AssignmentRejected("AGENT_NOT_ELIGIBLE")

        team_id = agent["team_id"]

        route = (
            session.execute(
                select(queue_routes).where(
                    and_(
                        queue_routes.c.ticket_id == ticket["ticket_id"],
                        queue_routes.c.cycle_no == ticket["cycle_no"],
                    )
                )
            )
            .mappings()
            .one_or_none()
        )

        if (
            route is not None
            and route["team_id"] is not None
            and route["team_id"] != team_id
        ):
            raise AssignmentRejected("ROUTE_TEAM_MISMATCH")

        route_revision = route["revision"] if route else 0

        record_queue_route(
            session,
            ticket["ticket_id"],
            RouteCommand(
                expected_revision=ticket["version"],
                cycle_no=ticket["cycle_no"],
                expected_route_revision=route_revision,
                team_id=UUID(str(team_id)),
            ),
            service_id="backend-b",
        )

        assignment = assign_handoff_ticket(
            session,
            ticket_id=ticket["ticket_id"],
            agent_id=agent_id,
            expected_revision=ticket["version"],
            reason_code="HUMAN_REQUEST",
        )

        result = session.execute(
            update(automation_jobs)
            .where(
                automation_jobs.c.job_id == current_job["job_id"],
                automation_jobs.c.status == "RUNNING",
                automation_jobs.c.lease_token == job["lease_token"],
                automation_jobs.c.lease_owner == worker_id,
                automation_jobs.c.lease_until > utcnow(),
                automation_jobs.c.expected_ticket_version == ticket["version"],
                automation_jobs.c.cycle_no == ticket["cycle_no"],
            )
            .values(
                status="HANDED_OFF",
                lease_token=None,
                lease_owner=None,
                lease_until=None,
                error_code=None,
                updated_at=utcnow(),
            )
        )

        if result.rowcount != 1:
            raise AssignmentRejected("HANDOFF_JOB_CONFLICT")

        return {
            "job_id": current_job["job_id"],
            "status": "HANDED_OFF",
            "assignment": assignment,
        }
