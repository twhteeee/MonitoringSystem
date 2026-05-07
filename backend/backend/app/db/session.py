"""
Async database session management.

Engine is created once at startup and shared across all requests.
Each request gets its own AsyncSession from the session factory —
never share sessions across requests or background tasks.

Usage (inside an endpoint via dependency injection):
    async def my_endpoint(db: AsyncSession = Depends(get_db)):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

def _build_engine() -> AsyncEngine:
    """
    Build the async SQLAlchemy engine.

    NullPool is used for Azure Container Apps where each replica manages
    its own connections. For single-instance deployments, switch to
    AsyncAdaptedQueuePool with pool_size/max_overflow.
    """
    kwargs: dict = {
        "echo": settings.db_echo,
        "pool_pre_ping": True,
    }

    if settings.environment == "production":
        kwargs.update(
            {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_recycle": settings.db_pool_recycle_seconds,
                "pool_timeout": 30,
            }
        )
    else:
        # NullPool avoids connection issues in tests and dev hot-reload
        kwargs["poolclass"] = NullPool

    return create_async_engine(settings.database_url, **kwargs)


engine: AsyncEngine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# --------------------------------------------------------------------------- #
# FastAPI dependency
# --------------------------------------------------------------------------- #

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a database session per request.
    Rolls back on exception, always closes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# --------------------------------------------------------------------------- #
# Context manager for use outside of FastAPI (background tasks, scripts)
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# --------------------------------------------------------------------------- #
# Lifecycle helpers (called from app lifespan)
# --------------------------------------------------------------------------- #

async def connect_db() -> None:
    """Verify the engine can reach the database at startup."""
    try:
        async with engine.begin() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("db.connected", url=settings.db_server)
    except Exception as exc:
        logger.error("db.connection_failed", error=str(exc))
        raise


async def disconnect_db() -> None:
    """Dispose the engine pool at shutdown."""
    await engine.dispose()
    logger.info("db.disconnected")
