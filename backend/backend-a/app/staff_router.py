from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app import automation_control as control
from app import exception_queue as queue
from app import retention, staff_detail, workload
from app.dependencies import DB, SnapshotDB, SnapshotUser, User
from app.errors import APIError
from app.resolution import WorkRejected
from app.routers import Cursor, Limit
from app.staff_models import automation_control_history, staff_permissions
from app.workload_schemas import WorkloadPage

router = APIRouter(prefix="/api/v1/staff", tags=["staff operations"])


class ControlState(BaseModel):
    paused: bool
    revision: int
    generation: int
    reason_code: str
    changed_by: UUID | None
    changed_at: datetime


class QueueCounts(BaseModel):
    total: int
    counts: dict[str, int]
    as_of: datetime


class StaffCapabilities(BaseModel):
    capabilities: list[
        Literal[
            "EXCEPTION_QUEUE_READ",
            "UNROUTED_QUEUE_READ",
            "AUTOMATION_READ",
            "AUTOMATION_STOP",
            "AUTOMATION_RESUME",
            "RETENTION_TEAM_REVIEW",
            "RETENTION_GLOBAL_REVIEW",
            "WORKLOAD_READ",
        ]
    ]


@router.get("/capabilities", response_model=StaffCapabilities)
def capabilities(session: SnapshotDB, user: SnapshotUser):
    if user["role"] not in {"ADMIN", "AGENT"}:
        raise APIError(403, "STAFF_ROLE_REQUIRED", user["user_id"])
    allowed = (
        {"EXCEPTION_QUEUE_READ"}
        if user["role"] == "AGENT"
        else {
            "EXCEPTION_QUEUE_READ",
            "UNROUTED_QUEUE_READ",
            "AUTOMATION_READ",
            "AUTOMATION_STOP",
            "AUTOMATION_RESUME",
            "RETENTION_TEAM_REVIEW",
            "RETENTION_GLOBAL_REVIEW",
            "WORKLOAD_READ",
        }
    )
    granted = session.scalars(
        select(staff_permissions.c.permission).where(staff_permissions.c.user_id == user["user_id"])
    )
    return {"capabilities": sorted(set(granted) & allowed)}


@router.get("/workload", response_model=WorkloadPage)
def workload_view(
    session: SnapshotDB,
    user: SnapshotUser,
    team_id: UUID | None = None,
    agent_id: UUID | None = None,
    include_unrouted: bool = False,
    limit: Limit = 20,
    cursor: Cursor = None,
):
    return workload.view(
        session,
        user,
        team_id=str(team_id) if team_id else None,
        agent_id=str(agent_id) if agent_id else None,
        include_unrouted=include_unrouted,
        limit=limit,
        cursor=cursor,
    )


@router.post("/retention/dry-run", response_model=retention.RetentionReport)
def retention_preview(body: retention.RetentionRequest, session: SnapshotDB, user: SnapshotUser):
    return retention.build_report(session, user, body)


@router.get("/exception-queue", response_model=queue.QueuePage)
def queue_list(
    session: SnapshotDB,
    user: SnapshotUser,
    queue_scope: queue.QueueScope = "ROUTED",
    reason: queue.QueueReason | None = None,
    team_id: UUID | None = None,
    limit: Limit = 20,
    cursor: Cursor = None,
):
    return queue.view(
        session,
        user,
        scope=queue_scope,
        reason=reason,
        team_id=str(team_id) if team_id else None,
        limit=limit,
        cursor=cursor,
    )


@router.get("/exception-queue/counts", response_model=QueueCounts)
def queue_counts(
    session: SnapshotDB,
    user: SnapshotUser,
    queue_scope: queue.QueueScope = "ROUTED",
    reason: queue.QueueReason | None = None,
    team_id: UUID | None = None,
):
    return queue.view(
        session,
        user,
        scope=queue_scope,
        reason=reason,
        team_id=str(team_id) if team_id else None,
        counts_only=True,
    )


@router.post("/tickets/{ticket_id}/internal", response_model=staff_detail.StaffTicketDetail)
def internal(ticket_id: UUID, body: staff_detail.DetailPurpose, session: SnapshotDB, user: SnapshotUser):
    return staff_detail.detail(session, user, str(ticket_id), body)


@router.get("/automation-control", response_model=ControlState)
def get_control(session: SnapshotDB, user: SnapshotUser):
    control.capability(session, user, "AUTOMATION_READ", admin=True)
    try:
        row = control.read_control(session)
    except WorkRejected:
        raise APIError(503, "AUTOMATION_CONTROL_UNAVAILABLE") from None
    return {k: row[k] for k in ControlState.model_fields}


@router.get("/automation-control/history", response_model=list[ControlState])
def history(
    session: SnapshotDB,
    user: SnapshotUser,
    limit: Limit = 20,
    before_revision: Annotated[int | None, Query(ge=1)] = None,
):
    control.capability(session, user, "AUTOMATION_READ", admin=True)
    query = (
        select(automation_control_history).order_by(automation_control_history.c.revision.desc()).limit(limit)
    )
    if before_revision is not None:
        query = query.where(automation_control_history.c.revision < before_revision)
    return [dict(r) for r in session.execute(query).mappings()]


@router.post("/automation-control/stop", response_model=ControlState)
def stop(body: control.StopCommand, session: DB, user: User):
    return control.change(session, user, body)


@router.post("/automation-control/resume", response_model=ControlState)
def resume(body: control.ResumeCommand, session: DB, user: User):
    return control.change(session, user, body, resume=True)
