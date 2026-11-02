from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app import analytics_service as service
from app import analytics_views as views
from app.analytics_auth import Publisher, Receiver
from app.analytics_schemas import BatchStatus, KpiResponse, ProductDetail, Submission, VocList
from app.dependencies import DB, SnapshotDB, SnapshotUser

router = APIRouter(prefix="/api/v1", tags=["analytics"])


@router.post("/analytics/batches", response_model=BatchStatus)
def receive_batch(body: Submission, request: Request, session: DB, identity: Receiver):
    return service.receive(session, body, identity, request.app.state.settings.analytics_max_rows)


@router.get("/analytics/batches/{batch_id}", response_model=BatchStatus)
def get_batch(batch_id: UUID, session: DB, identity: Receiver):
    return service.status(session, str(batch_id))


@router.post("/analytics/batches/{batch_id}/validate", response_model=BatchStatus)
def validate_batch(batch_id: UUID, session: DB, identity: Receiver):
    return service.validate(session, str(batch_id), identity)


@router.post("/analytics/batches/{batch_id}/publish", response_model=BatchStatus)
def publish_batch(batch_id: UUID, session: DB, identity: Publisher):
    return service.publish(session, str(batch_id), identity)


Teams = Annotated[list[UUID] | None, Query(max_length=8)]


@router.get("/admin/analytics/voc/top", response_model=VocList)
def voc_top(
    request: Request,
    session: SnapshotDB,
    user: SnapshotUser,
    team_ids: Teams = None,
    batch_id: UUID | None = None,
):
    return views.voc_list(
        session, views.resolve_snapshot(session, user, request.app.state.settings, team_ids, batch_id)
    )


@router.get("/admin/analytics/voc/unavailable", response_model=VocList)
def voc_unavailable(
    request: Request,
    session: SnapshotDB,
    user: SnapshotUser,
    team_ids: Teams = None,
    batch_id: UUID | None = None,
):
    return views.voc_list(
        session, views.resolve_snapshot(session, user, request.app.state.settings, team_ids, batch_id), True
    )


@router.get("/admin/analytics/products/{product_id}", response_model=ProductDetail)
def detail(
    product_id: UUID,
    request: Request,
    session: SnapshotDB,
    user: SnapshotUser,
    team_ids: Teams = None,
    batch_id: UUID | None = None,
):
    return views.product_detail(
        session,
        views.resolve_snapshot(session, user, request.app.state.settings, team_ids, batch_id),
        product_id,
    )


@router.get("/admin/analytics/kpi", response_model=KpiResponse)
def kpi(
    request: Request,
    session: SnapshotDB,
    user: SnapshotUser,
    team_ids: Teams = None,
    batch_id: UUID | None = None,
):
    return views.operational_kpi(
        session, views.resolve_snapshot(session, user, request.app.state.settings, team_ids, batch_id)
    )
