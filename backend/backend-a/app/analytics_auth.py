from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.errors import APIError

ISSUER = "csflow-analytics-service"
AUDIENCE = "csflow-analytics-ingest"
service_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="AnalyticsServiceBearer",
    description="Separate service JWT/key/issuer/audience; allowlisted subject and analytics permissions. User/admin login JWT is rejected.",
)


def service_identity(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(service_bearer)]
):
    settings = request.app.state.settings
    if not settings.analytics_service_secret or not settings.analytics_service_ids:
        raise APIError(503, "ANALYTICS_SERVICE_AUTH_NOT_CONFIGURED")
    if not credentials:
        raise APIError(401, "SERVICE_AUTHENTICATION_REQUIRED")
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.analytics_service_secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["sub", "iss", "aud", "exp", "iat", "nbf"]},
        )
        if claims["sub"] not in settings.analytics_service_ids:
            raise ValueError()
        permissions = claims.get("permissions", [])
        if not isinstance(permissions, list) or any(not isinstance(p, str) for p in permissions):
            raise ValueError()
        return {"id": claims["sub"], "permissions": permissions}
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise APIError(401, "INVALID_SERVICE_CREDENTIALS") from None


def receiver(identity: Annotated[dict, Depends(service_identity)]):
    if "analytics:receive" not in identity["permissions"]:
        raise APIError(403, "SERVICE_PERMISSION_REQUIRED")
    return identity


def publisher(identity: Annotated[dict, Depends(service_identity)]):
    if "analytics:publish" not in identity["permissions"]:
        raise APIError(403, "SERVICE_PERMISSION_REQUIRED")
    return identity


Receiver = Annotated[dict, Depends(receiver)]
Publisher = Annotated[dict, Depends(publisher)]
