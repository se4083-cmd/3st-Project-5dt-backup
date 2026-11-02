from datetime import timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.db import utcnow
from app.errors import APIError

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
# Equal-cost verification for unknown, inactive, and disabled fixture accounts.
dummy_hash = hasher.hash("unusable-dummy-verification-value")


def hash_password(password: str):
    return hasher.hash(password)


def verify_password(password: str, stored_hash: str):
    usable = stored_hash.startswith("$argon2")
    try:
        valid = hasher.verify(stored_hash if usable else dummy_hash, password)
        return usable and valid
    except (VerificationError, InvalidHashError):
        return False


def issue_token(user_id, settings):
    now = utcnow()
    return jwt.encode(
        {
            "sub": user_id,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=settings.token_minutes),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def token_subject(token, settings):
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "iat", "nbf", "exp", "iss", "aud"]},
        )
        return str(UUID(payload["sub"]))
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise APIError(401, "INVALID_CREDENTIALS") from None
