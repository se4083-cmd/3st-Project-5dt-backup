"""Project canonical JSON v1: UTC dates, stable decimals/keys and PK-sorted row arrays."""

import hashlib
import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.analytics_schemas import KEYS, TABLES, Submission


def normalize(value):
    if isinstance(value, BaseModel):
        return normalize(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Nonfinite number")
        return format(value.normalize(), "f") if value else "0"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite number")
        return int(value) if value.is_integer() else value
    return value


def digest(value):
    return hashlib.sha256(
        json.dumps(
            normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def canonical_submission(submission: Submission):
    value = normalize(submission)
    manifest = value["manifest"]
    for key in ("team_ids", "product_ids"):
        manifest[key].sort()
    for scope in manifest["scopes"]:
        scope["team_ids"].sort()
    manifest["scopes"].sort(key=lambda s: s["scope_key"])
    for table in TABLES:
        value["payload"][table].sort(key=lambda row: tuple(str(row[k]) for k in KEYS[table]))
    return value


def table_hashes(payload):
    return {
        table: digest(
            sorted(normalize(payload[table]), key=lambda row: tuple(str(row[k]) for k in KEYS[table]))
        )
        for table in TABLES
    }
