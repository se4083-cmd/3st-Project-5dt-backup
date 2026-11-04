from datetime import timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import select

from app import automation_monitor, voc_effects
from app.analytics_auth import service_identity
from app.dependencies import DB, SnapshotDB, SnapshotUser
from app.effect_models import effect_batches
from app.effect_schemas import EffectResult, EffectStatus, EffectSubmission
from app.errors import APIError
from app.monitor_schemas import AutomationMetrics

router = APIRouter(prefix="/api/v1", tags=["prospective monitoring / versioned VOC effects"])


def effect_receiver(identity: Annotated[dict, Depends(service_identity)]):
    if "voc-effects:receive" not in identity["permissions"]:
        raise APIError(403, "SERVICE_PERMISSION_REQUIRED")
    return identity


def effect_publisher(identity: Annotated[dict, Depends(service_identity)]):
    if "voc-effects:publish" not in identity["permissions"]:
        raise APIError(403, "SERVICE_PERMISSION_REQUIRED")
    return identity


Receiver = Annotated[dict, Depends(effect_receiver)]
Publisher = Annotated[dict, Depends(effect_publisher)]


@router.get("/staff/quality/automation-metrics", response_model=AutomationMetrics)
def diagnostics(
    session: SnapshotDB,
    user: SnapshotUser,
    request: Request,
    response_start: AwareDatetime,
    response_end: AwareDatetime,
    team_ids: Annotated[list[UUID] | None, Query(max_length=64)] = None,
    include_unattributed: bool = False,
    origin: Literal["APPLICATION", "SYNTHETIC", "UNKNOWN"] = "APPLICATION",
):
    if "as_of" in request.query_params:
        raise APIError(422, "QUALITY_CURRENT_SNAPSHOT_ONLY")
    return automation_monitor.metrics(
        session,
        user,
        response_start.astimezone(timezone.utc),
        response_end.astimezone(timezone.utc),
        [str(t) for t in team_ids] if team_ids is not None else None,
        include_unattributed,
        origin,
    )


@router.post("/analytics/voc-effects/batches", response_model=EffectStatus)
def receive(body: EffectSubmission, session: DB, identity: Receiver, request: Request):
    return voc_effects.receive(session, body, identity, request.app.state.settings)


@router.get("/analytics/voc-effects/batches/{batch_id}", response_model=EffectStatus)
def status(batch_id: UUID, session: DB, identity: Receiver):
    return voc_effects.status(session, str(batch_id))


@router.post("/analytics/voc-effects/batches/{batch_id}/validate", response_model=EffectStatus)
def validate(batch_id: UUID, session: DB, identity: Receiver):
    return voc_effects.validate(session, str(batch_id), identity)


@router.post("/analytics/voc-effects/batches/{batch_id}/publish", response_model=EffectStatus)
def publish(batch_id: UUID, session: DB, identity: Publisher, request: Request):
    origin = session.scalar(select(effect_batches.c.origin).where(effect_batches.c.batch_id == str(batch_id)))
    if (
        origin == "OPERATIONAL"
        and identity["id"] not in request.app.state.settings.voc_effect_operational_ids
    ):
        raise APIError(403, "EFFECT_OPERATIONAL_SOURCE_NOT_ALLOWED")
    return voc_effects.publish(session, str(batch_id), identity)


@router.get("/staff/voc-improvements/{action_id}/effects", response_model=EffectResult)
def effect_view(
    action_id: UUID,
    session: SnapshotDB,
    user: SnapshotUser,
    plan_revision: Annotated[int | None, Query(ge=1)] = None,
    origin: Literal["OPERATIONAL", "SYNTHETIC"] = "OPERATIONAL",
):
    return voc_effects.view(session, user, str(action_id), plan_revision, origin)
