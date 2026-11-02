from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app import models as m
from app import repository, retention
from app.analytics_models import analytics_publication, analytics_receipts
from app.retention import RetentionRequest, build_report
from app.seed import stable_id
from tests.analytics_helpers import small_batch
from tests.conftest import login_as
from tests.phase7_helpers import AS_OF, BODY, OLD, URL, archived, business_hashes, grant, target
from tests.test_finalization_contract import require_postgres


def stored_batch(factory, *, at=OLD, current=False, published=False):
    bid = str(uuid4())
    with factory.begin() as s:
        s.execute(
            m.analytics_batches.insert().values(
                batch_id=bid,
                status="VALIDATED" if published else "FAILED",
                source_as_of=OLD,
                created_at=at,
                updated_at=at,
                row_counts={},
                checksums={},
                schema_version="analytics-v1",
                is_current=False,
                manifest={},
            )
        )
        s.execute(
            m.analytics_daily.insert().values(
                **{
                    **small_batch()["payload"]["analytics_daily"][0],
                    "day": OLD.date(),
                    "batch_id": bid,
                    "created_at": at,
                    "updated_at": at,
                }
            )
        )
        s.execute(
            analytics_receipts.insert().values(
                batch_id=bid,
                content_hash="1" * 64,
                payload={"snapshot": "PRIVATE_RETENTION_RECEIPT"},
                validation_result={},
                received_at=at,
            )
        )
        if published:
            s.execute(
                m.analytics_batches.update()
                .where(m.analytics_batches.c.batch_id == bid)
                .values(
                    status="SUCCEEDED",
                    published_at=at,
                    validation_passed=True,
                    validated_at=at,
                    content_hash="1" * 64,
                    is_current=current,
                )
            )
        if current:
            if s.scalar(select(analytics_publication.c.singleton_id)):
                s.execute(analytics_publication.update().values(batch_id=bid))
            else:
                s.execute(analytics_publication.insert().values(singleton_id=1, batch_id=bid))
    return bid


@pytest.mark.postgres
def test_current_and_previous_published_and_failed_receipts_are_not_deletable(client, app):
    require_postgres(app)
    f = app.state.session_factory
    stored_batch(f, current=True, published=True)
    stored_batch(f, published=True)
    stored_batch(f)
    grant(f)
    h = login_as(client, "admin")
    before = business_hashes(f)
    r = client.post(URL, headers=h, json=BODY)
    assert r.status_code == 200
    assert "PRIVATE_RETENTION" not in r.text
    for name in ["analytics_batches", "analytics_receipts", "analytics_daily"]:
        t = target(r.json(), name)
        assert t["past_retention_count"] == 3 and t["candidate_count"] == 0
        assert t["blocked_count"] == 1 and t["requires_design_change_count"] == 2
        assert t["reason_counts"]["PUBLISHED_IMMUTABILITY_TRIGGER"] == 2
    assert target(r.json(), "analytics_receipts")["reason_counts"]["RECEIPT_IMMUTABILITY_TRIGGER"] == 3
    assert before == business_hashes(f)


@pytest.mark.postgres
@pytest.mark.parametrize("offset,expected", [(-1, 1), (0, 0), (1, 0)])
def test_aggregate_storage_clock_exact_boundary_not_old_source_as_of(client, app, offset, expected):
    require_postgres(app)
    f = app.state.session_factory
    stored_batch(f, at=AS_OF - timedelta(days=90) + timedelta(microseconds=offset))
    grant(f)
    report = client.post(URL, headers=login_as(client, "admin"), json=BODY).json()
    assert target(report, "analytics_daily")["past_retention_count"] == expected
    # Receipt uses raw/extract 30d; aggregate uses90d, both report explicit fields.
    assert target(report, "analytics_receipts")["past_retention_count"] == 1
    assert target(report, "analytics_daily")["age_basis"].startswith("analytics_daily.created_at")


@pytest.mark.postgres
def test_authenticated_request_uses_one_snapshot_despite_concurrent_changes(client, app, monkeypatch):
    require_postgres(app)
    f = app.state.session_factory
    tid, _ = archived(f)
    grant(f)
    h = login_as(client, "admin")
    read, release = Event(), Event()
    original = retention.inspect

    def pause(session, **kw):
        item = original(session, **kw)
        if kw["table"] is m.messages:
            read.set()
            assert release.wait(10)
        return item

    monkeypatch.setattr(retention, "inspect", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: client.post(URL, headers=h, json=BODY))
        try:
            assert read.wait(5)
            archived(f)
            with f.begin() as s:
                s.execute(
                    m.tickets.update()
                    .where(m.tickets.c.ticket_id == tid)
                    .values(status="PROCESSING", resolved_at=None, resolution_mode=None)
                )
        finally:
            release.set()
        response = future.result(timeout=10)
    assert response.status_code == 200
    report = response.json()
    assert target(report, "messages")["inspected_count"] == 1
    assert target(report, "tickets")["inspected_count"] == 1
    assert target(report, "tickets")["reason_counts"].get("UNRESOLVED_TICKET", 0) == 0
    monkeypatch.setattr(retention, "inspect", original)
    next_report = client.post(URL, headers=h, json=BODY).json()
    assert target(next_report, "messages")["inspected_count"] == 2
    assert target(next_report, "tickets")["reason_counts"]["UNRESOLVED_TICKET"] == 1


@pytest.mark.postgres
def test_same_repeatable_read_scope_policy_asof_is_reproducible_and_sql_is_aggregate_only(client, app):
    require_postgres(app)
    f = app.state.session_factory
    tid, _ = archived(f, cycle=1)
    grant(f, permission="RETENTION_TEAM_REVIEW")
    with (
        app.state.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c,
        Session(bind=c) as s,
    ):
        s.info["snapshot_as_of"] = s.scalar(text("SELECT transaction_timestamp()"))
        user = repository.get_user(s, stable_id("admin"))
        command = RetentionRequest(**{**BODY, "scope": "TEAM"})
        statements = []

        def capture(conn, cursor, statement, params, context, many):
            statements.append(statement)

        event.listen(c, "before_cursor_execute", capture)
        first = build_report(s, user, command)
        with f.begin() as writer:
            writer.execute(
                m.tickets.update()
                .where(m.tickets.c.ticket_id == tid)
                .values(status="PROCESSING", resolved_at=None, resolution_mode=None)
            )
        second = build_report(s, user, command)
        assert first.result_fingerprint == second.result_fingerprint
        assert first.targets == second.targets
        assert any("count(" in sql.lower() for sql in statements)
        for sql in statements:
            assert not any(
                v in sql.lower()
                for v in [
                    "messages.body",
                    "ai_suggestions.draft",
                    "analytics_receipts.payload",
                    "followup_actions.internal_note",
                    "idempotency_keys.response_snapshot",
                    "customers.profile_masked",
                ]
            )
        event.remove(c, "before_cursor_execute", capture)
        s.rollback()  # this test's audit writes are intentionally rolled back
