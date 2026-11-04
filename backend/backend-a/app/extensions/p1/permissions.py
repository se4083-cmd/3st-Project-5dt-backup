from sqlalchemy import select

from app import automation_control
from app.analytics_canonical import digest
from app.errors import APIError
from app.model_constraints import user_team_scopes
from app.models import teams
from app.staff_models import PERMISSIONS, staff_permissions


def allowed_teams(session, user, selected=None):
    if user["role"] != "ADMIN":
        raise APIError(403, "ADMIN_ROLE_REQUIRED", user["user_id"])
    allowed = set(
        session.scalars(
            select(user_team_scopes.c.team_id)
            .join(teams)
            .where(user_team_scopes.c.user_id == user["user_id"], teams.c.active.is_(True))
        )
    )
    chosen = list(map(str, selected)) if selected is not None else sorted(allowed)
    if len(set(chosen)) != len(chosen):
        raise APIError(422, "DUPLICATE_TEAM_FILTER")
    if not chosen or not set(chosen) <= allowed:
        raise APIError(403, "P1_TEAM_SCOPE_DENIED", user["user_id"])
    return sorted(chosen)


def require_monitor(session, user, selected=None):
    automation_control.capability(session, user, "P1_MONITOR_READ", admin=True)
    return allowed_teams(session, user, selected)


def capabilities(session, user):
    return sorted(
        set(
            session.scalars(
                select(staff_permissions.c.permission).where(staff_permissions.c.user_id == user["user_id"])
            )
        )
        & set(PERMISSIONS)
    )


def ui_session(session, user):
    team_ids = allowed_teams(session, user)
    grants = capabilities(session, user)
    permissions = ["OPERATIONS_READ", "PRODUCT_READ"]
    if "P1_MONITOR_READ" in grants:
        permissions.append("P1_MONITOR_READ")
    if "AUTOMATION_READ" in grants:
        permissions.append("AUTOMATION_MANAGE")
    return dict(
        userId=user["user_id"],
        displayName="관리자",
        role="ADMIN",
        active=True,
        permissions=permissions,
        allowedTeamIds=team_ids,
        scopeKey=digest(team_ids),
        capabilities=grants,
    )
