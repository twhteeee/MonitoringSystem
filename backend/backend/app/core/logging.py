"""
Structured logging setup using structlog.

All log entries are emitted as JSON in production and as coloured
console output in development. Traces are forwarded to Azure
Application Insights via the opencensus exporter when a connection
string is configured.

Usage
-----
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("signal.query", machine_id="M01", signal="Ramp1", rows=240)
"""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

from app.core.config import get_settings

settings = get_settings()


# --------------------------------------------------------------------------- #
# Processors
# --------------------------------------------------------------------------- #

def add_app_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Inject static application context into every log entry."""
    event_dict.setdefault("service", settings.app_name)
    event_dict.setdefault("version", settings.app_version)
    event_dict.setdefault("environment", settings.environment)
    return event_dict


def add_request_id(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Pull request_id from structlog context vars if present.
    The request_id is injected by RequestContextMiddleware.
    """
    from structlog.contextvars import get_contextvars
    ctx = get_contextvars()
    if "request_id" in ctx:
        event_dict["request_id"] = ctx["request_id"]
    return event_dict


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def configure_logging() -> None:
    """
    Configure structlog and standard library logging.
    Call once at application startup (inside lifespan).
    """
    log_level = getattr(logging, settings.log_level, logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        add_app_context,
        add_request_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.environment == "development":
        # Human-readable, coloured output for local dev
        renderer: Any = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON for production — consumed by Azure Monitor / Log Analytics
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Silence noisy third-party loggers
    for name in ("azure", "urllib3", "httpx", "asyncio", "aioodbc"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Azure Application Insights exporter
    if settings.appinsights_connection_string:
        _configure_app_insights()


def _configure_app_insights() -> None:
    """Attach opencensus Azure exporter to the root logger."""
    try:
        from opencensus.ext.azure.log_exporter import AzureLogHandler
        ai_handler = AzureLogHandler(
            connection_string=settings.appinsights_connection_string
        )
        logging.getLogger().addHandler(ai_handler)
    except ImportError:
        logging.getLogger(__name__).warning(
            "opencensus-ext-azure not installed — App Insights disabled"
        )


# --------------------------------------------------------------------------- #
# Public factory
# --------------------------------------------------------------------------- #

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[return-value]


def new_request_id() -> str:
    return str(uuid.uuid4())
