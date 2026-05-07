"""
FastAPI application entry point.

Startup order
-------------
1. Configure structured logging
2. Connect Redis cache
3. Verify database connectivity
4. Register middleware (order matters — outermost runs first)
5. Mount API router
6. Expose /health endpoint (no auth — used by Azure health probes)

Shutdown order
--------------
1. Disconnect Redis
2. Dispose SQLAlchemy engine pool
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import orjson
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import connect_db, disconnect_db
from app.middleware.request_context import RequestContextMiddleware
from app.schemas.common import ErrorDetail, ErrorResponse, HealthResponse
from app.services.cache_service import cache

settings = get_settings()
logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ---- startup ----
    configure_logging()
    logger.info(
        "app.starting",
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )

    await cache.connect()
    await connect_db()

    logger.info("app.ready")
    yield

    # ---- shutdown ----
    logger.info("app.shutting_down")
    await cache.disconnect()
    await disconnect_db()
    logger.info("app.stopped")


# --------------------------------------------------------------------------- #
# Application factory
# --------------------------------------------------------------------------- #

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Factory machine monitoring API. "
            "Consumes KEPServer data from Azure SQL and exposes it via "
            "REST and WebSocket endpoints to the React dashboard."
        ),
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
        default_response_class=_ORJSONResponse,
    )

    # ---- middleware (registered in reverse — last added = outermost) ----

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    app.add_middleware(RequestContextMiddleware)

    # ---- exception handlers ----

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        from structlog.contextvars import get_contextvars
        request_id = get_contextvars().get("request_id", "unknown")
        logger.error("app.unhandled_exception", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                request_id=request_id,
                errors=[
                    ErrorDetail(
                        code="INTERNAL_SERVER_ERROR",
                        message="An unexpected error occurred.",
                    )
                ],
            ).model_dump(),
        )

    # ---- routers ----

    app.include_router(api_router)

    # ---- health ----

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Health check — used by Azure load balancer probes",
        include_in_schema=False,
    )
    async def health() -> HealthResponse:
        db_ok = "ok"
        cache_ok = "ok"

        try:
            from sqlalchemy import text
            from app.db.session import engine
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            db_ok = "error"

        cache_ok = "ok" if await cache.ping() else "error"

        overall = "ok" if db_ok == "ok" and cache_ok == "ok" else "degraded"

        return HealthResponse(
            status=overall,
            version=settings.app_version,
            environment=settings.environment,
            db=db_ok,
            cache=cache_ok,
        )

    return app


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

class _ORJSONResponse(JSONResponse):
    """Use orjson for faster serialisation — handles datetime natively."""

    media_type = "application/json"

    def render(self, content: object) -> bytes:
        return orjson.dumps(content, option=orjson.OPT_NON_STR_KEYS)


# --------------------------------------------------------------------------- #
# ASGI entrypoint
# --------------------------------------------------------------------------- #

app = create_app()
