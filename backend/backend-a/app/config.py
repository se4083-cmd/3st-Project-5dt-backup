import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = Field(repr=False)
    jwt_secret: str = Field(min_length=32, repr=False)
    jwt_issuer: str = "cs-flow-ai"
    jwt_audience: str = "cs-flow-api"
    token_minutes: int = Field(default=30, ge=1, le=120)
    cors_origins: list[str] = []
    voc_effect_operational_ids: list[str] = []
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    pool_size: int = Field(default=5, ge=1, le=30)
    max_overflow: int = Field(default=5, ge=0, le=30)
    pool_timeout: int = Field(default=10, ge=1, le=60)
    db_connect_timeout: int = Field(default=5, ge=1, le=30)
    db_statement_timeout_ms: int = Field(default=10000, ge=500, le=60000)
    enable_dev_seed: bool = False
    analytics_service_secret: str | None = Field(default=None, min_length=48, repr=False)
    analytics_service_ids: list[str] = []
    analytics_max_bytes: int = Field(default=8_000_000, ge=100, le=20_000_000)
    analytics_max_rows: int = Field(default=20000, ge=1, le=100000)
    analytics_stale_hours: int = Field(default=24, ge=1, le=720)

    @model_validator(mode="after")
    def secure_environment(self):
        if self.analytics_service_secret and (
            self.analytics_service_secret == self.jwt_secret
            or any(
                x in self.analytics_service_secret.lower()
                for x in ("replace", "changeme", "default", "example")
            )
        ):
            raise ValueError("Use a separate randomly generated analytics service secret")
        secret = self.jwt_secret.lower()
        if any(x in secret for x in ("replace", "changeme", "default", "example")):
            raise ValueError("JWT_SECRET must be generated before startup")
        url = make_url(self.database_url)
        if url.drivername not in ("postgresql+psycopg", "sqlite+pysqlite"):
            raise ValueError("Use postgresql+psycopg or explicit development sqlite+pysqlite")
        if self.app_env == "production":
            if self.enable_dev_seed or any(x in secret for x in ("dev", "test", "local", "synthetic")):
                raise ValueError("Development settings are prohibited in production")
            if len(set(self.jwt_secret)) < 16 or len(self.jwt_secret) < 48:
                raise ValueError("Production signing secret must have at least 48 random characters")
            if url.drivername != "postgresql+psycopg" or url.query.get("sslmode") != "verify-full":
                raise ValueError("Production requires PostgreSQL with sslmode=verify-full and a trusted CA")
            if "*" in self.allowed_hosts or not self.allowed_hosts:
                raise ValueError("Production ALLOWED_HOSTS must be explicit")
            if any(not x.startswith("https://") or "*" in x for x in self.cors_origins):
                raise ValueError("Production CORS origins must be explicit HTTPS origins")
        return self


@lru_cache
def get_settings():
    return Settings(_env_file=os.environ.get("CSFLOW_ENV_FILE", ".env"))
