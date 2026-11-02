"""Singleton lock is acquired AFTER ticket/job by workers; commands never lock jobs."""

from typing import Literal

from pydantic import Field
from sqlalchemy import select

from app import audit
from app.db import utcnow
from app.errors import APIError
from app.models import users
from app.resolution import WorkRejected
from app.schemas import Input
from app.staff_models import automation_control as control
from app.staff_models import automation_control_history as history
from app.staff_models import staff_permissions


class StopCommand(Input):
    expected_revision: int = Field(ge=1)
    reason_code: Literal["SAFETY_INCIDENT", "OPERATOR_PAUSE"]


class ResumeCommand(Input):
    expected_revision: int = Field(ge=1)
    stopped_revision: int = Field(ge=1)
    reason_code: Literal["VERIFICATION_COMPLETE", "INCIDENT_RESOLVED"]


def capability(session, user, permission, *, admin=False):
    if user["role"] not in ({"ADMIN"} if admin else {"ADMIN", "AGENT"}) or not session.scalar(
        select(staff_permissions.c.user_id).where(
            staff_permissions.c.user_id == user["user_id"], staff_permissions.c.permission == permission
        )
    ):
        raise APIError(403, "EXPLICIT_PERMISSION_REQUIRED", user["user_id"])


def read_control(session, *, shared=False):
    query = select(control).where(control.c.singleton_id == 1)
    if shared:
        query = query.with_for_update(read=True)
    row = session.execute(query).mappings().first()
    if not row:
        raise WorkRejected("AUTOMATION_CONTROL_UNAVAILABLE")
    return row


def assert_automatic_allowed(session, generation):
    row = read_control(session, shared=True)
    if row["paused"]:
        raise WorkRejected("AUTOMATION_PAUSED")
    if row["generation"] != generation:
        raise WorkRejected("AUTOMATION_GENERATION_CHANGED")
    return row


def change(session, user, body, *, resume=False):
    # actor user -> control, never ticket/job. No inversion with worker's
    # ticket -> job -> control SHARE. Audit FK does not lock business tickets.
    current = (
        session.execute(
            select(users).where(users.c.user_id == user["user_id"]).with_for_update(key_share=True)
        )
        .mappings()
        .one()
    )
    if not current["active"]:
        raise APIError(401, "INVALID_CREDENTIALS")
    capability(session, current, "AUTOMATION_RESUME" if resume else "AUTOMATION_STOP", admin=True)
    row = (
        session.execute(select(control).where(control.c.singleton_id == 1).with_for_update())
        .mappings()
        .first()
    )
    if not row:
        raise APIError(503, "AUTOMATION_CONTROL_UNAVAILABLE")
    if row["revision"] != body.expected_revision:
        raise APIError(409, "AUTOMATION_REVISION_CONFLICT")
    if resume:
        if not row["paused"] or body.stopped_revision != row["revision"]:
            raise APIError(409, "STOPPED_REVISION_REQUIRED")
    elif row["paused"]:
        raise APIError(409, "AUTOMATION_ALREADY_PAUSED")
    values = dict(
        paused=not resume,
        revision=row["revision"] + 1,
        generation=row["generation"] + 1,
        reason_code=body.reason_code,
        changed_by=user["user_id"],
        changed_at=utcnow(),
    )
    with session.begin_nested():
        session.execute(control.update().where(control.c.singleton_id == 1).values(**values))
        session.execute(history.insert().values(**values))
        audit.record(
            session,
            user["user_id"],
            "AUTOMATION_RESUMED" if resume else "AUTOMATION_STOPPED",
            "AUTOMATION_CONTROL",
            None,
            reason=body.reason_code,
        )
    return values
