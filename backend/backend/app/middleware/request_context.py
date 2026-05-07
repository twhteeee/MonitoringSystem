"""
Request context middleware.

Responsibilities:
1. Generate a unique request_id (UUID) for every incoming request.
2. Bind request_id into structlog's context vars so every log line
   emitted during request handling carries it automatically.
3. Inject X-Request-ID into the response headers (useful for tracing
   in Azure Application Insights and for client-side error reporting).
4. Log request start / end with latency at INFO level.
5. Forward request_id to App Insights operation context when available.
"""

from __future__ import annotations

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.logging import get_logger, new_request_id

logger = get_logger(__name__)

# Paths that generate too much noise in logs — skip detailed logging
_SILENT_PATHS = {"/health", "/metrics", "/favicon.ico"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Always clear previous request's context vars first
        clear_contextvars()

        request_id = request.headers.get("X-Request-ID") or new_request_id()
        bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        silent = request.url.path in _SILENT_PATHS
        start = time.perf_counter()

        if not silent:
            logger.info(
                "request.start",
                client=request.client.host if request.client else "unknown",
                query=str(request.url.query) or None,
            )

        response: Response
        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.error(
                "request.unhandled_exception",
                error=str(exc),
                elapsed_ms=elapsed_ms,
                exc_info=True,
            )
            raise

        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

        response.headers["X-Request-ID"] = request_id

        if not silent:
            logger.info(
                "request.end",
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
            )

        clear_contextvars()
        return response
