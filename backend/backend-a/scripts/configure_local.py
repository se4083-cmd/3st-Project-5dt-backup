"""Create an ignored local .env with random keys; never overwrite an existing configuration."""

import argparse
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", action="store_true", help="Explicit no-PostgreSQL development fallback")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env"
    template = (root / ".env.example").read_text(encoding="utf-8")
    template = template.replace(
        "replace-with-a-random-secret-at-least-32-characters", secrets.token_urlsafe(64)
    )
    template = template.replace("replace-with-a-local-database-password", secrets.token_urlsafe(32))
    if args.sqlite:
        template = (
            "\n".join(
                "DATABASE_URL=sqlite+pysqlite:///./csflow.db" if line.startswith("DATABASE_URL=") else line
                for line in template.splitlines()
            )
            + "\n"
        )
    with destination.open("x", encoding="utf-8") as output:
        output.write(template)
    print("Created ignored .env with random local secrets. Run migrations, then explicit development seed.")


if __name__ == "__main__":
    main()
