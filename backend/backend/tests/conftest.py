"""
Shared pytest fixtures.

Test database
-------------
Integration tests run against a real in-process SQLite database
(via aiosqlite) rather than Azure SQL, so no cloud credentials are
needed in CI. The schema is created fresh for every test session.

For tests that exercise SQL Server-specific SQL (window functions,
DATEADD), use the @pytest.mark.mssql marker and configure a test
Azure SQL instance in the CI pipeline via DB_* environment variables.

Authentication
--------------
JWT validation is bypassed in the test client by overriding the
get_current_user dependency with a factory that returns a pre-built
TokenPayload with a given role.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.security import Role, TokenPayload, get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.cache_service import cache

# --------------------------------------------------------------------------- #
# Database fixtures
# --------------------------------------------------------------------------- #

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


# --------------------------------------------------------------------------- #
# Token / auth fixtures
# --------------------------------------------------------------------------- #

def make_token(role: Role = Role.ADMIN) -> TokenPayload:
    return TokenPayload(
        sub="test-user-id",
        oid="test-user-id",
        name="Test User",
        preferred_username="test@factory.com",
        roles=[role.value],
    )


@pytest.fixture
def admin_token() -> TokenPayload:
    return make_token(Role.ADMIN)


@pytest.fixture
def viewer_token() -> TokenPayload:
    return make_token(Role.VIEWER)


# --------------------------------------------------------------------------- #
# FastAPI test client
# --------------------------------------------------------------------------- #

@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> FastAPI:
    """Application with DB and auth overridden for testing."""
    test_app = create_app()

    # Override DB dependency
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    # Override auth — return admin by default; individual tests can re-override
    async def override_get_current_user() -> TokenPayload:
        return make_token(Role.ADMIN)

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = override_get_current_user

    return test_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# --------------------------------------------------------------------------- #
# Cache fixture — mock Redis so unit tests never need a real Redis
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def mock_cache(monkeypatch):
    """
    Replace the global cache singleton with a no-op mock for all tests.
    Integration tests that explicitly test caching behaviour should
    override this fixture locally.
    """
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    mock.delete = AsyncMock()
    mock.invalidate_machine = AsyncMock()
    mock.get_signals = AsyncMock(return_value=None)
    mock.set_signals = AsyncMock()
    mock.get_latest = AsyncMock(return_value=None)
    mock.set_latest = AsyncMock()
    mock.ping = AsyncMock(return_value=True)

    # Patch at the module level where it's imported
    import app.services.machine_service as ms_mod
    import app.services.signal_service as ss_mod
    monkeypatch.setattr(ms_mod, "cache", mock)
    monkeypatch.setattr(ss_mod, "cache", mock)
    return mock
