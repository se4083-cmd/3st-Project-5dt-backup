"""Explicit local/test grant; never activates accounts or modifies P0 control."""

import argparse

from sqlalchemy import select

from app.config import get_settings
from app.db import build_engine, session_factory
from app.model_constraints import user_team_scopes
from app.models import teams, users
from app.staff_models import staff_permissions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login-name", required=True)
    args = parser.parse_args()
    settings = get_settings()
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Use the team's permission process for production")
    engine = build_engine(settings)
    try:
        with session_factory(engine).begin() as session:
            user = (
                session.execute(select(users).where(users.c.login_name == args.login_name)).mappings().one()
            )
            if not user["active"] or user["role"] != "ADMIN":
                raise SystemExit("Active ADMIN required; no account activation is performed")
            if not session.scalar(
                select(user_team_scopes.c.team_id)
                .join(teams)
                .where(user_team_scopes.c.user_id == user["user_id"], teams.c.active.is_(True))
            ):
                raise SystemExit("Existing active SQL team grant required")
            if not session.scalar(
                select(staff_permissions.c.user_id).where(
                    staff_permissions.c.user_id == user["user_id"],
                    staff_permissions.c.permission == "P1_MONITOR_READ",
                )
            ):
                session.execute(
                    staff_permissions.insert().values(user_id=user["user_id"], permission="P1_MONITOR_READ")
                )
        print("P1_MONITOR_READ granted. AUTOMATION_READ/STOP/RESUME require separate explicit grants.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
