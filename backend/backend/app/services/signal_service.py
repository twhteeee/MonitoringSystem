"""
Signal service — time-series data retrieval, downsampling, and threshold checks.

Downsampling strategy
---------------------
Range        Raw rows est.   Bucket minutes   Max returned
15m / 1h     60–3600         None (raw)       all
6h / 24h     >3600           auto (≤500 pts)  ≤ 500
7d / 30d     >50 000         auto (≤500 pts)  ≤ 500

For ranges longer than 6h the service delegates to aggregated SQL queries
instead of fetching all raw rows. This keeps response sizes predictable
regardless of KEPServer write frequency.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.machine_repository import (
    MachineRepository,
    SignalDefinitionRepository,
)
from app.repositories.signal_repository import SignalRepository
from app.schemas.signal import (
    AggregatedSignalData,
    LatestReading,
    MachineLatestReadings,
    MultiMachineSignalResponse,
    RawReading,
    SignalData,
    TimeRange,
    RANGE_HOURS,
)
from app.services.cache_service import cache

logger = get_logger(__name__)

# Ranges where aggregation kicks in instead of raw rows
_AGGREGATE_RANGES: set[TimeRange] = {"6h", "24h", "7d", "30d"}
_TARGET_POINTS = 500    # target resolution for downsampled responses


class SignalService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SignalRepository(session)
        self._machine_repo = MachineRepository(session)
        self._sig_def_repo = SignalDefinitionRepository(session)

    # ------------------------------------------------------------------ #
    # Validate signal names against definitions
    # ------------------------------------------------------------------ #

    async def _validate_signals(
        self, machine_id: str, requested: list[str]
    ) -> None:
        defined = set(await self._sig_def_repo.get_names_for_machine(machine_id))
        if not defined:
            # Machine exists but has no definitions configured yet — allow
            return
        unknown = set(requested) - defined
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown signals for machine '{machine_id}': {sorted(unknown)}. "
                       f"Defined signals: {sorted(defined)}.",
            )

    # ------------------------------------------------------------------ #
    # Raw readings
    # ------------------------------------------------------------------ #

    async def get_raw(
        self,
        machine_id: str,
        signals: list[str],
        range_: TimeRange,
        resolution: int | None,
        quality_filter: bool,
    ) -> list[SignalData]:
        await self._machine_repo.get_or_raise(machine_id)
        await self._validate_signals(machine_id, signals)

        cached = await cache.get_signals(machine_id, signals, range_, quality_filter)
        if cached:
            logger.debug("cache.hit", machine_id=machine_id, range=range_)
            return [SignalData(**s) for s in cached]

        readings = await self._repo.get_raw(
            machine_id, signals, range_=range_, quality_filter=quality_filter
        )

        # Group by signal name
        groups: dict[str, list[RawReading]] = {s: [] for s in signals}
        for r in readings:
            groups.setdefault(r.signal_name, []).append(
                RawReading(timestamp=r.timestamp, value=r.value, quality=r.quality)
            )

        # Apply thin-plate downsampling if resolution is requested
        if resolution:
            groups = {
                name: _downsample(pts, resolution)
                for name, pts in groups.items()
            }

        # Fetch units from definitions
        units = {
            d.signal_name: d.unit
            for d in await self._sig_def_repo.get_by_machine(machine_id)
        }

        result = [
            SignalData(
                machine_id=machine_id,
                signal_name=sig,
                unit=units.get(sig),
                readings=groups.get(sig, []),
            )
            for sig in signals
        ]

        await cache.set_signals(
            machine_id,
            signals,
            range_,
            quality_filter,
            [s.model_dump(mode="json") for s in result],
        )
        return result

    # ------------------------------------------------------------------ #
    # Aggregated readings
    # ------------------------------------------------------------------ #

    async def get_aggregated(
        self,
        machine_id: str,
        signal_name: str,
        range_: TimeRange,
    ) -> AggregatedSignalData:
        await self._machine_repo.get_or_raise(machine_id)

        bucket_minutes = _bucket_minutes_for_range(range_)
        readings = await self._repo.get_aggregated(
            machine_id, signal_name, range_, bucket_minutes
        )

        sig_def = await self._sig_def_repo.get_by_machine_and_name(
            machine_id, signal_name
        )

        return AggregatedSignalData(
            machine_id=machine_id,
            signal_name=signal_name,
            unit=sig_def.unit if sig_def else None,
            bucket_minutes=bucket_minutes,
            readings=readings,
        )

    # ------------------------------------------------------------------ #
    # Latest readings (live tiles)
    # ------------------------------------------------------------------ #

    async def get_latest(
        self,
        machine_id: str,
        signals: list[str] | None = None,
    ) -> MachineLatestReadings:
        machine = await self._machine_repo.get_or_raise(machine_id)

        cached = await cache.get_latest(machine_id)
        if cached:
            return MachineLatestReadings(**cached)

        readings_orm = await self._repo.get_latest_per_signal(machine_id, signals)
        sig_defs = {
            d.signal_name: d
            for d in await self._sig_def_repo.get_by_machine(machine_id)
        }

        latest: list[LatestReading] = []
        for r in readings_orm:
            defn = sig_defs.get(r.signal_name)
            is_alarm = is_warning = False
            if defn:
                if defn.alarm_low is not None and r.value < defn.alarm_low:
                    is_alarm = True
                if defn.alarm_high is not None and r.value > defn.alarm_high:
                    is_alarm = True
                if defn.warn_low is not None and r.value < defn.warn_low:
                    is_warning = True
                if defn.warn_high is not None and r.value > defn.warn_high:
                    is_warning = True

            latest.append(
                LatestReading(
                    machine_id=machine_id,
                    signal_name=r.signal_name,
                    value=r.value,
                    quality=r.quality,
                    timestamp=r.timestamp,
                    unit=defn.unit if defn else None,
                    is_alarm=is_alarm,
                    is_warning=is_warning,
                )
            )

        result = MachineLatestReadings(
            machine_id=machine_id,
            machine_name=machine.name,
            readings=latest,
        )
        await cache.set_latest(machine_id, result.model_dump(mode="json"))
        return result

    # ------------------------------------------------------------------ #
    # Multi-machine query
    # ------------------------------------------------------------------ #

    async def get_multi_machine(
        self,
        machine_ids: list[str],
        signals: list[str],
        range_: TimeRange,
        resolution: int | None,
        quality_filter: bool,
    ) -> MultiMachineSignalResponse:
        all_data: list[SignalData] = []
        for mid in machine_ids:
            machine_data = await self.get_raw(
                mid, signals, range_, resolution, quality_filter
            )
            all_data.extend(machine_data)

        total = sum(len(s.readings) for s in all_data)
        return MultiMachineSignalResponse(
            machines=all_data,
            queried_at=datetime.now(tz=timezone.utc),
            range=range_,
            total_points=total,
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _bucket_minutes_for_range(range_: TimeRange) -> int:
    """Choose a bucket size that produces ~500 points for the given range."""
    total_minutes = int(RANGE_HOURS[range_] * 60)
    raw = total_minutes / _TARGET_POINTS
    # Round up to a clean interval
    for candidate in [1, 2, 5, 10, 15, 30, 60, 120, 360, 720, 1440]:
        if candidate >= raw:
            return candidate
    return 1440


def _downsample(points: list[RawReading], target: int) -> list[RawReading]:
    """
    Largest-Triangle-Three-Buckets (LTTB) downsampling.
    Preserves visual shape better than uniform thinning.
    """
    n = len(points)
    if n <= target:
        return points

    sampled: list[RawReading] = [points[0]]
    bucket_size = (n - 2) / (target - 2)

    for i in range(target - 2):
        avg_start = int((i + 1) * bucket_size) + 1
        avg_end = min(int((i + 2) * bucket_size) + 1, n)
        avg_x = sum(range(avg_start, avg_end)) / (avg_end - avg_start)
        avg_y = sum(p.value for p in points[avg_start:avg_end]) / (avg_end - avg_start)

        range_start = int(i * bucket_size) + 1
        range_end = min(int((i + 1) * bucket_size) + 1, n)

        prev = sampled[-1]
        prev_idx = range_start - 1

        max_area = -1.0
        max_idx = range_start

        for j in range(range_start, range_end):
            area = abs(
                (prev_idx - avg_x) * (points[j].value - prev.value)
                - (prev_idx - j) * (avg_y - prev.value)
            ) * 0.5
            if area > max_area:
                max_area = area
                max_idx = j

        sampled.append(points[max_idx])

    sampled.append(points[-1])
    return sampled
