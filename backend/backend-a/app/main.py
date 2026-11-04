import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import audit
from app.analytics_limits import AnalyticsBodyLimit
from app.analytics_router import router as analytics_router
from app.config import Settings, get_settings
from app.db import build_engine, session_factory
from app.errors import APIError
from app.extensions.p1.policy_router import router as policy_router
from app.extensions.p1.router import router as p1_router
from app.extensions.p1.voc_router import router as voc_router
from app.operations_router import router as operations_router
from app.public_limits import PublicLimits
from app.routers import router
from app.schemas import ErrorEnvelope
from app.staff_router import router as staff_router

logger = logging.getLogger("csflow.api")


def create_app(settings: Settings | None = None):
    settings = settings or get_settings()
    engine = build_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(
        title="CS Flow AI Backend A",
        version="0.7.1",
        debug=False,
        lifespan=lifespan,
        # Python3.12/3.13 use different HTTPStatus phrases for413/422.
        # Fix only these descriptions; the checker still compares the entire
        # OpenAPI including all fields, schemas, responses and permissions.
        responses={
            s: {
                "model": ErrorEnvelope,
                **(
                    {"description": {413: "Content Too Large", 422: "Unprocessable Content"}[s]}
                    if s in (413, 422)
                    else {}
                ),
            }
            for s in (401, 403, 404, 409, 413, 422, 429, 503)
        },
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory(engine)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(AnalyticsBodyLimit, max_bytes=settings.analytics_max_bytes)
    if settings.app_env == "production":
        app.add_middleware(PublicLimits, analytics_bytes=settings.analytics_max_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Location", "Idempotency-Replayed"],
    )

    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        # No access log of raw URL/query/body/headers. Fixed code + correlation only.
        logger.info("request_completed id=%s status=%s", request.state.request_id, response.status_code)
        return response

    def error_response(request, status, code):
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
        return JSONResponse(
            status_code=status,
            headers=headers,
            content={"error": {"code": code, "request_id": request.state.request_id}},
        )

    @app.exception_handler(APIError)
    def api_error(request: Request, exc: APIError):
        if exc.status in (401, 403, 404):
            audit.record_denial(app.state.session_factory, exc)
        return error_response(request, exc.status, exc.code)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # Pydantic's raw errors may include the original submitted secret/message.
        return error_response(request, 422, "VALIDATION_ERROR")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, exc.status_code, "HTTP_" + str(exc.status_code))

    @app.exception_handler(SQLAlchemyError)
    def database_error(request, exc):
        logger.error("database_operation_failed id=%s", request.state.request_id)
        return error_response(request, 503, "DATABASE_UNAVAILABLE")

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error("request_failed id=%s", request.state.request_id)
        return error_response(request, 500, "INTERNAL_ERROR")

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"])
    def ready(request: Request):
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != "0010":
                return error_response(request, 503, "MIGRATIONS_REQUIRED")
        return {"status": "ready"}

    app.include_router(router)
    app.include_router(operations_router)
    app.include_router(analytics_router)
    app.include_router(staff_router)
    app.include_router(p1_router)
    app.include_router(voc_router)
    app.include_router(policy_router)
    return app
