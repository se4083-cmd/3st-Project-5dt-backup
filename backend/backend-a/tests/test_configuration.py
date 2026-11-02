import secrets

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.seed import require_development


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret": "replace-with-a-random-secret-at-least-32-characters"},
        {"app_env": "production"},
        {"app_env": "production", "database_url": "postgresql+psycopg://x:x@localhost/x?sslmode=require"},
        {
            "app_env": "production",
            "database_url": "postgresql+psycopg://x:x@localhost/x?sslmode=verify-full",
            "enable_dev_seed": True,
        },
        {
            "app_env": "production",
            "database_url": "postgresql+psycopg://x:x@localhost/x?sslmode=verify-full",
            "cors_origins": ["*"],
        },
    ],
)
def test_insecure_configuration_rejected(overrides):
    config = dict(
        _env_file=None, database_url="sqlite+pysqlite:///:memory:", jwt_secret=secrets.token_urlsafe(64)
    )
    config.update(overrides)
    with pytest.raises(ValidationError):
        Settings(**config)


def test_production_seed_prohibited_even_if_manually_called():
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret=secrets.token_urlsafe(64),
        database_url="postgresql+psycopg://x:x@db.example.test/db?sslmode=verify-full",
    )
    with pytest.raises(ValueError):
        require_development(settings)


def test_live_without_database_readiness_fails(tmp_path):
    settings = Settings(
        _env_file=None,
        app_env="test",
        jwt_secret=secrets.token_urlsafe(64),
        database_url="sqlite+pysqlite:///" + (tmp_path / "not-migrated.db").as_posix(),
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
