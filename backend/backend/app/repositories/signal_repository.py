"""
Signal repository — time-series data access against signal_readings.

All queries are optimised for the (machine_id, signal_name, timestamp)
composite index defined on the model.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import SignalReading
from app.repositories.base import BaseRepository
from app.schemas.signal import AggregatedReading, RANGE_HOURS, TimeRange


class SignalRepository(BaseRepository[SignalReading]):
    model = SignalReading

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _since(range_: TimeRange) -> datetime:
        hours = RANGE_HOURS[range_]
        return datetime.now(tz=timezone.utc) - timedelta(hours=hours)

    # ------------------------------------------------------------------ #
    # Raw reads
    # ------------------------------------------------------------------ #

    async def get_raw(
        self,
        machine_id: str,
        signals: list[str],
        range_: TimeRange = "1h",
        quality_filter: bool = True,
    ) -> list[SignalReading]:
        """
        Return all raw readings for the given signals within the time range.
        Filtered to OPC quality 192 (Good) by default.
        """
        since = self._since(range_)
        filters = [
            SignalReading.machine_id == machine_id,
            SignalReading.signal_name.in_(signals),
            SignalReading.timestamp >= since,
        ]
        if quality_filter:
            filters.append(SignalReading.quality == 192)

        result = await self.session.execute(
            select(SignalReading)
            .where(and_(*filters))
            .order_by(SignalReading.signal_name, SignalReading.timestamp.asc())
        )
        return list(result.scalars().all())

    async def get_latest_per_signal(
        self,
        machine_id: str,
        signals: list[str] | None = None,
    ) -> list[SignalReading]:
        """
        Return the most recent reading for each signal of a machine.
        Uses a window function (ROW_NUMBER) for a single round-trip.
        """
        # Subquery: rank readings by timestamp descending within each signal
        subq = (
            select(
                SignalReading,
                func.row_number()
                .over(
                    partition_by=SignalReading.signal_name,
                    order_by=SignalReading.timestamp.desc(),
                )
                .label("rn"),
            )
            .where(SignalReading.machine_id == machine_id)
        )
        if signals:
            subq = subq.where(SignalReading.signal_name.in_(signals))

        subq = subq.subquery()

        result = await self.session.execute(
            select(SignalReading)
            .join(subq, SignalReading.id == subq.c.id)
            .where(subq.c.rn == 1)
        )
        return list(result.scalars().all())

    async def get_latest_for_all_machines(
        self, machine_ids: list[str], signal_name: str
    ) -> list[SignalReading]:
        """Cross-machine latest value for a single signal — used by overview tiles."""
        subq = (
            select(
                SignalReading,
                func.row_number()
                .over(
                    partition_by=SignalReading.machine_id,
                    order_by=SignalReading.timestamp.desc(),
                )
                .label("rn"),
            )
            .where(
                SignalReading.machine_id.in_(machine_ids),
                SignalReading.signal_name == signal_name,
            )
            .subquery()
        )
        result = await self.session.execute(
            select(SignalReading)
            .join(subq, SignalReading.id == subq.c.id)
            .where(subq.c.rn == 1)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------ #
    # Downsampled / aggregated reads
    # ------------------------------------------------------------------ #

    async def get_aggregated(
        self,
        machine_id: str,
        signal_name: str,
        range_: TimeRange,
        bucket_minutes: int,
    ) -> list[AggregatedReading]:
        """
        Server-side time-bucketed aggregation using T-SQL DATEADD/DATEDIFF.
        Returns min/avg/max per bucket for smooth long-range chart rendering.
        """
        since = self._since(range_)

        # T-SQL expression to truncate timestamp to bucket boundary
        bucket_expr = text(
            f"DATEADD(minute, (DATEDIFF(minute, '2000-01-01', timestamp) "
            f"/ {bucket_minutes}) * {bucket_minutes}, '2000-01-01')"
        )

        rows = await self.session.execute(
            select(
                bucket_expr.label("bucket_start"),
                func.min(SignalReading.value).label("min_value"),
                func.avg(SignalReading.value).label("avg_value"),
                func.max(SignalReading.value).label("max_value"),
                func.count(SignalReading.id).label("sample_count"),
            )
            .where(
                SignalReading.machine_id == machine_id,
                SignalReading.signal_name == signal_name,
                SignalReading.timestamp >= since,
                SignalReading.quality == 192,
            )
            .group_by(bucket_expr)
            .order_by(bucket_expr)
        )

        return [
            AggregatedReading(
                bucket_start=row.bucket_start,
                min_value=round(row.min_value, 4),
                avg_value=round(row.avg_value, 4),
                max_value=round(row.max_value, 4),
                sample_count=row.sample_count,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------ #
    # Count (for pagination / telemetry)
    # ------------------------------------------------------------------ #

    async def count_by_machine(
        self, machine_id: str, range_: TimeRange = "24h"
    ) -> int:
        since = self._since(range_)
        result = await self.session.execute(
            select(func.count(SignalReading.id)).where(
                SignalReading.machine_id == machine_id,
                SignalReading.timestamp >= since,
            )
        )
        return result.scalar_one()
