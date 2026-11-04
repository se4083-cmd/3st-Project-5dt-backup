import os

from fastapi import Request
from pydantic_settings import BaseSettings, SettingsConfigDict


class P1Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="P1_", extra="ignore")
    enabled: bool = False


def enabled(request: Request):
    # Deliberately lazy: disabled P1 needs no Azure configuration or SDK.
    from app.errors import APIError

    if not P1Settings(_env_file=os.environ.get("CSFLOW_ENV_FILE", ".env")).enabled:
        raise APIError(503, "P1_DISABLED")
