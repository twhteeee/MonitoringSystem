"""
Redis cache service.

Provides typed get/set/delete/invalidate methods with a consistent
key naming convention:

    machine:{id}:signals:{sorted_names}:{range}:{quality}
    machine:{id}:latest
    machine:{id}:latest:{signal_name}
    machines:list
    machines:{id}

TTL is selected automatically based on the query time range:
    15m/1h  → short  (30s)
    6h/24h  → medium (5 min)
    7d/30d  → long   (30 min)
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.signal import TimeRange

settings = get_settings()
logger = get_logger(__name__)


class CacheService:
    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        await self._client.ping()
        logger.info("cache.connected", url=settings.redis_url)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            logger.info("cache.disconnected")

    # ------------------------------------------------------------------ #
    # TTL strategy
    # ------------------------------------------------------------------ #

    def _ttl(self, range_: TimeRange) -> int:
        if range_ in ("15m", "1h"):
            return settings.redis_ttl_short_seconds
        if range_ in ("6h", "24h"):
            return settings.redis_ttl_medium_seconds
        return settings.redis_ttl_long_seconds

    # ------------------------------------------------------------------ #
    # Generic helpers
    # ------------------------------------------------------------------ #

    async def get(self, key: str) -> Any | None:
        if not self._client:
            return None
        try:
            raw = await self._client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("cache.get_error", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        if not self._client:
            return
        try:
            await self._client.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as exc:
            logger.warning("cache.set_error", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        if not self._client:
            return
        try:
            await self._client.delete(key)
        except Exception as exc:
            logger.warning("cache.delete_error", key=key, error=str(exc))

    async def invalidate_machine(self, machine_id: str) -> None:
        """Flush all cache keys related to a machine."""
        if not self._client:
            return
        pattern = f"machine:{machine_id}:*"
        try:
            keys = await self._client.keys(pattern)
            if keys:
                await self._client.delete(*keys)
            logger.debug("cache.invalidated", pattern=pattern, count=len(keys))
        except Exception as exc:
            logger.warning("cache.invalidate_error", pattern=pattern, error=str(exc))

    async def ping(self) -> bool:
        if not self._client:
            return False
        try:
            return (await self._client.ping()) is True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Domain-specific keys
    # ------------------------------------------------------------------ #

    @staticmethod
    def signal_key(
        machine_id: str,
        signals: list[str],
        range_: TimeRange,
        quality_filter: bool,
    ) -> str:
        names = ",".join(sorted(signals))
        q = "good" if quality_filter else "all"
        return f"machine:{machine_id}:signals:{names}:{range_}:{q}"

    @staticmethod
    def latest_key(machine_id: str, signal_name: str | None = None) -> str:
        if signal_name:
            return f"machine:{machine_id}:latest:{signal_name}"
        return f"machine:{machine_id}:latest"

    @staticmethod
    def machines_list_key() -> str:
        return "machines:list"

    @staticmethod
    def machine_key(machine_id: str) -> str:
        return f"machine:{machine_id}"

    # ------------------------------------------------------------------ #
    # Typed helpers used by services
    # ------------------------------------------------------------------ #

    async def get_signals(
        self, machine_id: str, signals: list[str], range_: TimeRange, quality: bool
    ) -> Any | None:
        key = self.signal_key(machine_id, signals, range_, quality)
        return await self.get(key)

    async def set_signals(
        self,
        machine_id: str,
        signals: list[str],
        range_: TimeRange,
        quality: bool,
        value: Any,
    ) -> None:
        key = self.signal_key(machine_id, signals, range_, quality)
        await self.set(key, value, ttl=self._ttl(range_))

    async def get_latest(self, machine_id: str) -> Any | None:
        return await self.get(self.latest_key(machine_id))

    async def set_latest(self, machine_id: str, value: Any) -> None:
        await self.set(
            self.latest_key(machine_id),
            value,
            ttl=settings.redis_ttl_realtime_seconds,
        )


# Singleton — created at startup, shared across all requests
cache = CacheService()
