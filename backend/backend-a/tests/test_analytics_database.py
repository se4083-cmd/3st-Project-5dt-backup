from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
from queue import Queue
from threading import Event
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, func, select, text
from sqlalchemy.exc import DBAPIError

from app import analytics_service as service
from app import analytics_views as views
from app import models, seed
from app.analytics_models import analytics_publication, analytics_receipts
from app.analytics_schemas import Submission
from app.db import build_engine, session_factory
from app.errors import APIError
from tests.analytics_helpers import READ, ROOT, publish, rehash, service_headers, small_batch, stage
from tests.conftest import ROOT as PROJECT_ROOT
from tests.conftest import login_as, migrate
from tests.test_finalization_contract import require_postgres, wait_for_blocker

IDENTITY = {"id": "local-contract-test"}


def newer(body, hours=1):
    value = deepcopy(body)
    value["manifest"]["batch_id"] = str(uuid4())
    old = datetime.fromisoformat(value["manifest"]["source_as_of"].replace("Z", "+00:00"))
    asof = (old + timedelta(hours=hours)).isoformat()
    value["manifest"].update(source_as_of=asof, generated_at=asof)
    for r in value["payload"]["analytics_product_risk"]:
        r["source_as_of"] = asof
    return rehash(value)


@pytest.mark.postgres
@pytest.mark.parametrize("new_first", [True, False])
def test_postgres_publish_race_real_pointer_lock(client, app, new_first):
    require_postgres(app)
    first = small_batch()
    second = newer(first)
    h = service_headers(app)
    for body in (first, second):
        stage(client, app, body)
        assert client.post(f"{ROOT}/{body['manifest']['batch_id']}/validate", headers=h).json()[
            "validation_passed"
        ]
    written, release, pid_queue = Event(), Event(), Queue()

    def run(body, hold=False):
        try:
            with app.state.session_factory.begin() as s:
                pid = s.scalar(text("SELECT pg_backend_pid()"))
                if not hold:
                    pid_queue.put(pid)
                service.publish(s, body["manifest"]["batch_id"], IDENTITY)
                if hold:
                    written.set()
                    assert release.wait(10)
            return "OK"
        except APIError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(run, second if new_first else first, True)
        try:
            assert written.wait(5)
            b = pool.submit(run, first if new_first else second)
            wait_for_blocker(app, pid_queue.get(timeout=5))
        finally:
            release.set()
        assert a.result(timeout=10) == "OK"
        assert b.result(timeout=10) == ("BATCH_NOT_NEWER" if new_first else "OK")
    with app.state.session_factory() as s:
        assert s.scalar(select(analytics_publication.c.batch_id)) == second["manifest"]["batch_id"]
        assert (
            s.scalar(
                select(func.count())
                .select_from(models.analytics_batches)
                .where(models.analytics_batches.c.is_current)
            )
            == 1
        )


@pytest.mark.postgres
@pytest.mark.parametrize("changed", [False, True])
def test_postgres_concurrent_receive(client, app, changed):
    require_postgres(app)
    body = small_batch()
    second = deepcopy(body)
    if changed:
        second["payload"]["analytics_daily"][0]["ticket_count"] += 1
        second = rehash(second)
    written, release, q = Event(), Event(), Queue()

    def run(value, hold=False):
        try:
            with app.state.session_factory.begin() as s:
                pid = s.scalar(text("SELECT pg_backend_pid()"))
                if not hold:
                    q.put(pid)
                service.receive(s, Submission.model_validate(value), IDENTITY, 20000)
                if hold:
                    written.set()
                    assert release.wait(10)
            return "OK"
        except APIError as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(run, body, True)
        try:
            assert written.wait(5)
            b = pool.submit(run, second)
            wait_for_blocker(app, q.get(timeout=5))
        finally:
            release.set()
        assert a.result(timeout=10) == "OK"
        assert b.result(timeout=10) == ("BATCH_CONTENT_CONFLICT" if changed else "OK")
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(analytics_receipts)) == 1


@pytest.mark.postgres
def test_postgres_read_snapshot_survives_publish_switch(client, app, monkeypatch):
    require_postgres(app)
    first, h = publish(client, app)
    second = newer(first)
    stage(client, app, second)
    client.post(f"{ROOT}/{second['manifest']['batch_id']}/validate", headers=h)
    admin = login_as(client, "admin")
    original = views.scoped_risks
    seen, release = Event(), Event()

    def paused(*args):
        seen.set()
        assert release.wait(10)
        return original(*args)

    monkeypatch.setattr(views, "scoped_risks", paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.get, READ + "/voc/top", headers=admin)
        try:
            assert seen.wait(5)
            assert (
                client.post(f"{ROOT}/{second['manifest']['batch_id']}/publish", headers=h).status_code == 200
            )
        finally:
            release.set()
        result = future.result(timeout=10).json()
    assert result["meta"]["batch_id"] == first["manifest"]["batch_id"]
    assert result["items"][0]["source_as_of"] == first["manifest"]["source_as_of"]
    monkeypatch.setattr(views, "scoped_risks", original)
    latest = client.get(READ + "/voc/top", headers=admin).json()
    assert latest["meta"]["batch_id"] == second["manifest"]["batch_id"]
    historical = client.get(
        READ + "/voc/top", params={"batch_id": first["manifest"]["batch_id"]}, headers=admin
    ).json()
    assert (
        not historical["meta"]["is_current"] and historical["meta"]["batch_id"] != latest["meta"]["batch_id"]
    )
    assert (
        client.post(f"{ROOT}/{first['manifest']['batch_id']}/publish", headers=h).json()["is_current"]
        is False
    )


@pytest.mark.postgres
@pytest.mark.parametrize(
    "table", ["analytics_batches", "analytics_receipts", "analytics_daily", "analytics_product_risk"]
)
def test_postgres_published_db_immutable(client, app, table):
    require_postgres(app)
    body, _ = publish(client, app)
    target = analytics_receipts if table == "analytics_receipts" else getattr(models, table)
    column = {
        "analytics_batches": "source_as_of",
        "analytics_receipts": "content_hash",
        "analytics_daily": "ticket_count",
        "analytics_product_risk": "rank",
    }[table]
    with pytest.raises(DBAPIError), app.state.session_factory.begin() as s:
        s.execute(
            target.update()
            .where(target.c.batch_id == body["manifest"]["batch_id"])
            .values({column: target.c[column]})
        )
        # An identical head update is harmless; force actual head change.
        if table == "analytics_batches":
            s.execute(
                target.update()
                .where(target.c.batch_id == body["manifest"]["batch_id"])
                .values(schema_version="tamper")
            )


def test_upgrade_preserves_populated_fixture_and_readiness(settings, monkeypatch, fixture_dir):
    migrate(settings, monkeypatch, "0003")
    engine = build_engine(settings)
    with session_factory(engine).begin() as s:
        seed.seed_fixture(s, fixture_dir)
        assert s.scalar(select(func.count()).select_from(models.analytics_product_risk)) == 300
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    command.check(Config(str(PROJECT_ROOT / "alembic.ini")))
    with session_factory(engine).begin() as s:
        assert s.scalar(select(func.count()).select_from(models.analytics_product_risk)) == 300
        assert s.scalar(select(models.analytics_batches.c.validation_passed)) is False
        assert s.scalar(select(analytics_publication.c.batch_id)) is None
    command.downgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "0003")
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    engine.dispose()


def test_history_downgrade_refused_and_ready(client, app):
    publish(client, app)
    assert client.get("/health/ready").json()["status"] == "ready"
    with pytest.raises(RuntimeError, match="lose analytics history"):
        command.downgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "0003")
    assert client.get("/health/ready").status_code == 200


def test_readiness_requires_new_revision(client, app):
    with app.state.engine.begin() as c:
        c.execute(text("UPDATE alembic_version SET version_num='0003'"))
    assert client.get("/health/ready").json()["error"]["code"] == "MIGRATIONS_REQUIRED"
    with app.state.engine.begin() as c:
        c.execute(text("UPDATE alembic_version SET version_num='0011'"))
    assert client.get("/health/ready").status_code == 200


def test_legacy_current_is_preserved_but_not_blessed(settings, monkeypatch):
    migrate(settings, monkeypatch, "0003")
    engine = build_engine(settings)
    old = Table("analytics_batches", MetaData(), autoload_with=engine)
    from app.db import utcnow

    bid = str(uuid4())
    with engine.begin() as c:
        c.execute(
            old.insert().values(
                batch_id=bid,
                status="SUCCEEDED",
                is_current=True,
                published_at=utcnow(),
                row_counts={},
                checksums={},
                schema_version="legacy",
                manifest={},
                data_origin="SYNTHETIC",
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    with engine.connect() as c:
        r = c.execute(select(models.analytics_batches)).mappings().one()
        assert r["status"] == "SUCCEEDED" and not r["is_current"] and not r["validation_passed"]
        assert c.scalar(select(analytics_publication.c.batch_id)) is None
    engine.dispose()


@pytest.mark.postgres
@pytest.mark.parametrize("publish_first", [True, False])
def test_postgres_raw_mart_update_cannot_race_publication(client, app, publish_first):
    require_postgres(app)
    body, h = stage(client, app)
    bid = body["manifest"]["batch_id"]
    assert client.post(f"{ROOT}/{bid}/validate", headers=h).json()["validation_passed"]
    written, release, q = Event(), Event(), Queue()

    def run(operation, hold=False):
        try:
            with app.state.session_factory.begin() as s:
                pid = s.scalar(text("SELECT pg_backend_pid()"))
                if not hold:
                    q.put(pid)
                if operation == "publish":
                    service.publish(s, bid, IDENTITY)
                else:
                    s.execute(
                        models.analytics_daily.update()
                        .where(models.analytics_daily.c.batch_id == bid)
                        .values(ticket_count=models.analytics_daily.c.ticket_count + 1)
                    )
                if hold:
                    written.set()
                    assert release.wait(10)
            return "OK"
        except APIError as e:
            return e.code
        except DBAPIError:
            return "IMMUTABLE"

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(run, "publish" if publish_first else "update", True)
        try:
            assert written.wait(5)
            b = pool.submit(run, "update" if publish_first else "publish")
            wait_for_blocker(app, q.get(timeout=5))
        finally:
            release.set()
        assert a.result(timeout=10) == "OK"
        assert b.result(timeout=10) == ("IMMUTABLE" if publish_first else "VALIDATED_PAYLOAD_CHANGED")
