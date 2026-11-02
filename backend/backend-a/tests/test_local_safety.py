import pytest

from app.local_guard import require_local_database
from scripts.local_support import local_environment, write_environment


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:secret@remote.example:5432/db",
        "postgresql+psycopg://u:secret@localhost:5432/db",
        "postgresql+psycopg://u:secret@127.0.0.1:5432/db?host=remote.example",
        "postgresql+psycopg://u:secret@127.0.0.1:5432/db?service=cloud",
        "postgresql+psycopg://u:secret@127.0.0.1:5432/db?hostaddr=8.8.8.8",
        "postgresql+psycopg://u:secret@127.0.0.1:5432/db?sslmode=prefer",
        "postgresql+psycopg://u:secret@127.0.0.1/db",
        "sqlite+pysqlite://///network/share/db",
        "postgresql+psycopg://u:p@127.0.0.1:5432/host%3Dremote.example",
    ],
    ids=[
        "remote",
        "implicit-host",
        "host-override",
        "service",
        "hostaddr",
        "tls",
        "implicit-port",
        "unc",
        "dbname-conninfo",
    ],
)
def test_local_fence_rejects_without_echo_or_connection(url):
    with pytest.raises(ValueError, match="^LOCAL_DATABASE_REQUIRED$"):
        require_local_database(url)


def test_local_environment_removes_credentials_and_proxies(monkeypatch):
    for name in ("AZURE_TOKEN", "OPENAI_API_KEY", "PGSERVICE", "DATABASE_URL", "HTTP_PROXY", "PYTHONPATH"):
        monkeypatch.setenv(name, "sensitive-sentinel")
    env = local_environment()
    assert all(
        key not in env for key in ("AZURE_TOKEN", "OPENAI_API_KEY", "PGSERVICE", "DATABASE_URL", "PYTHONPATH")
    )
    assert env["HTTP_PROXY"] == "" and env["CSFLOW_LOCAL_ONLY"] == "1"


def test_local_fence_permits_explicit_loopback_and_schema():
    require_local_database(
        "postgresql+psycopg://u:p@127.0.0.1:55432/db?sslmode=disable&options=-csearch_path=test_local",
        postgres_only=True,
    )


def test_local_password_roundtrip_does_not_change_or_inject_env(tmp_path):
    path = tmp_path / "local.env"
    value = 'synthetic # value "quoted"\nAZURE_TOKEN=not-a-configuration'
    write_environment(
        path,
        {
            "DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:55432/db?sslmode=disable",
            "DEV_SEED_PASSWORD": value,
        },
    )
    env = local_environment(path)
    assert env["DEV_SEED_PASSWORD"] == value and "AZURE_TOKEN" not in env


def test_engine_guard_runs_before_sqlalchemy_engine_creation(monkeypatch):
    from app import db
    from app.config import Settings

    monkeypatch.setenv("CSFLOW_LOCAL_ONLY", "1")

    def forbidden(*args, **kwargs):
        raise AssertionError("ENGINE_CREATION_MUST_NOT_RUN")

    monkeypatch.setattr(db, "create_engine", forbidden)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@remote.example:5432/db",
        jwt_secret="REVIEW_KEY_c0abf043b7cc157f6334a27b985cb71019abcec4f",
    )
    with pytest.raises(ValueError, match="^LOCAL_DATABASE_REQUIRED$"):
        db.build_engine(settings)


def test_explicit_env_file_ignores_default_dotenv(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DATABASE_URL=remote-invalid\n", encoding="utf-8")
    path = tmp_path / "isolated.env"
    write_environment(
        path,
        {
            "DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:55432/db?sslmode=disable",
            "JWT_SECRET": "REVIEW_KEY_c0abf043b7cc157f6334a27b985cb71019abcec4f",
        },
    )
    monkeypatch.setenv("CSFLOW_ENV_FILE", str(path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        assert require_local_database(get_settings().database_url).host == "127.0.0.1"
    finally:
        get_settings.cache_clear()
