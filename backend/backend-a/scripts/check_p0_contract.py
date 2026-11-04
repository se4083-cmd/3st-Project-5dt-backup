"""Compare every original operation, schema and security scheme against the archived P0 contract."""

import json
import secrets
from pathlib import Path

from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def check():
    baseline = json.loads((ROOT / "docs/p0-openapi.json").read_text(encoding="utf-8"))
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret=secrets.token_urlsafe(48),
        )
    )
    try:
        actual = app.openapi()
    finally:
        app.state.engine.dispose()
    for path, operations in baseline["paths"].items():
        assert actual["paths"].get(path) == operations, f"P0 operation changed: {path}"
    for group, values in baseline["components"].items():
        for name, value in values.items():
            assert actual["components"][group].get(name) == value, f"P0 {group} changed: {name}"
    count = sum(
        method in {"get", "post", "patch", "put", "delete"}
        for methods in baseline["paths"].values()
        for method in methods
    )
    print(
        f"PASS: {len(baseline['paths'])} P0 paths / {count} operations, all original component and security definitions unchanged"
    )


if __name__ == "__main__":
    check()
