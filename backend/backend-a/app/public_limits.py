"""Small single-worker team-dev ingress limits; no raw identifiers retained.

Limits are process-local, reset on restart, and must be replaced by a shared
ingress limiter before scaling out. Unknown X-Forwarded-For is never trusted.
"""

import hashlib
import json
import time
from collections import OrderedDict
from uuid import uuid4

from starlette.responses import JSONResponse


class PublicLimits:
    def __init__(self, app, *, body_bytes=131072, analytics_bytes=8000000, login_attempts=10):
        self.app = app
        self.body_bytes, self.analytics_bytes = body_bytes, analytics_bytes
        self.login_attempts = login_attempts
        self.buckets = OrderedDict()

    def allow(self, key, limit):
        now = time.monotonic()
        while self.buckets and next(iter(self.buckets.values()))[0] <= now - 60:
            self.buckets.popitem(last=False)
        start, count = self.buckets.get(key, (now, 0))
        if start <= now - 60:
            start, count = now, 0
        if key not in self.buckets and len(self.buckets) >= 4096:
            return False
        self.buckets[key] = (start, count + 1)
        return count < limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def reject(status, code):
            await JSONResponse(
                {
                    "error": {
                        "code": code,
                        "request_id": scope.get("state", {}).get("request_id", str(uuid4())),
                    }
                },
                status_code=status,
                headers={"Retry-After": "60"} if status == 429 else {},
            )(scope, receive, send)

        maximum = self.analytics_bytes if scope["path"] == "/api/v1/analytics/batches" else self.body_bytes
        parts, size = [], 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            chunk = event.get("body", b"")
            size += len(chunk)
            if size > maximum:
                return await reject(413, "REQUEST_TOO_LARGE")
            parts.append(chunk)
            if not event.get("more_body", False):
                break
        body = b"".join(parts)
        if scope["path"] == "/api/v1/auth/login" and scope["method"] == "POST":
            peer = str((scope.get("client") or ("unknown",))[0])
            try:
                value = json.loads(body)
                name = value.get("login_name", "") if isinstance(value, dict) else ""
                name = name.strip().casefold() if isinstance(name, str) else ""
            except (ValueError, UnicodeError):
                name = ""
            digest = hashlib.sha256(name.encode()).hexdigest()
            if not (
                self.allow("global", 120)
                and self.allow("peer:" + hashlib.sha256(peer.encode()).hexdigest(), 60)
                and self.allow("account:" + digest, self.login_attempts)
            ):
                return await reject(429, "LOGIN_RATE_LIMITED")
        sent = False

        async def bounded_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, bounded_receive, send)
