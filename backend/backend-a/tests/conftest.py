import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.main import create_app
from app.seed import seed_minimal

PASSWORD = "REVIEW_PW_4ce35ee7d58ba7b228434"
ROOT = Path(__file__).resolve().parents[1]


def pytest_addoption(parser):
    parser.addoption("--database", choices=["sqlite", "postgres"], default="sqlite")


@pytest.fixture
def fixture_dir():
    path = Path(os.environ.get("CSFLOW_FIXTURE_DIR", ROOT / "reference/fixture"))
    if not (path / "schema_contract.json").is_file():
        pytest.skip("External 22-table synthetic fixture not present; set CSFLOW_FIXTURE_DIR")
    return path


@pytest.fixture
def settings(tmp_path, request):
    if request.config.getoption("--database") == "postgres":
        url = os.environ.get("TEST_POSTGRES_URL")
        if not url:
            pytest.fail("--database=postgres requires TEST_POSTGRES_URL; no silent SQLite fallback")
        if os.environ.get("CSFLOW_LOCAL_ONLY") == "1":
            from app.local_guard import require_local_database

            require_local_database(url, postgres_only=True)
        schema = "test_csflow_" + uuid4().hex
        admin = create_engine(url, hide_parameters=True)
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = (
            make_url(url)
            .update_query_dict({"options": f"-csearch_path={schema}"})
            .render_as_string(hide_password=False)
        )
    else:
        url = "sqlite+pysqlite:///" + (tmp_path / "app.db").as_posix()
        admin = None
    yield Settings(
        _env_file=None,
        app_env="test",
        database_url=url,
        jwt_secret="REVIEW_TEST_KEY_6e7e8a395e7aab4d12615cb86fc5746ff39a85778d7fd1eb742",
        enable_dev_seed=True,
    )
    if admin is not None:
        with admin.begin() as conn:
            # Only the exact, freshly created test schema is removed.
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def migrate(settings, monkeypatch, target="head"):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    monkeypatch.setenv("JWT_SECRET", settings.jwt_secret)
    get_settings.cache_clear()
    command.upgrade(Config(str(ROOT / "alembic.ini")), target)
    get_settings.cache_clear()


@pytest.fixture
def app(settings, monkeypatch):
    migrate(settings, monkeypatch)
    app = create_app(settings)
    with app.state.session_factory.begin() as session:
        seed_minimal(session, PASSWORD)
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def headers(client):
    response = client.post(
        "/api/v1/auth/login", json={"login_name": "dev-customer1@example.test", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def login_as(client, label):
    response = client.post(
        "/api/v1/auth/login", json={"login_name": f"dev-{label}@example.test", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}
