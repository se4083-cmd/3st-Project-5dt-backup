"""Export the actual application contract without connecting to any database."""

import json
import secrets
from pathlib import Path

from app.config import Settings
from app.main import create_app


def main():
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret=secrets.token_urlsafe(48),
        )
    )
    target = Path(__file__).resolve().parents[1] / "docs/openapi.json"
    target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    app.state.engine.dispose()
    print("OpenAPI exported without network or database execution")


if __name__ == "__main__":
    main()
