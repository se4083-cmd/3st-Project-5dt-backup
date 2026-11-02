from uuid import uuid4

from starlette.responses import JSONResponse


class AnalyticsBodyLimit:
    """Bound bytes before JSON decoding, including chunked/misreported bodies."""

    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/api/v1/analytics/batches"
        ):
            return await self.app(scope, receive, send)
        parts, count = [], 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            count += len(event.get("body", b""))
            if count > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "ANALYTICS_UPLOAD_TOO_LARGE",
                            "request_id": scope.get("state", {}).get("request_id", str(uuid4())),
                        }
                    },
                )
                return await response(scope, receive, send)
            parts.append(event.get("body", b""))
            if not event.get("more_body", False):
                break
        sent = False

        async def bounded_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"".join(parts), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
