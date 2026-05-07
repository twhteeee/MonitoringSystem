"""Unit tests for SignalService — including LTTB downsampling."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models.signal import SignalReading
from app.schemas.signal import RawReading
from app.services.signal_service import SignalService, _downsample


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _ts(minute: int) -> datetime:
    return datetime(2024, 6, 1, 8, minute, 0, tzinfo=timezone.utc)


def _reading(signal: str, value: float, minute: int = 0, quality: int = 192) -> SignalReading:
    r = SignalReading()
    r.id = minute
    r.machine_id = "M01"
    r.signal_name = signal
    r.value = value
    r.quality = quality
    r.timestamp = _ts(minute)
    return r


# --------------------------------------------------------------------------- #
# LTTB downsampling
# --------------------------------------------------------------------------- #

class TestDownsample:
    def test_returns_all_if_under_target(self):
        pts = [RawReading(timestamp=_ts(i), value=float(i), quality=192) for i in range(10)]
        result = _downsample(pts, 50)
        assert result == pts

    def test_returns_exact_target_count(self):
        pts = [RawReading(timestamp=_ts(i), value=float(i) ** 2, quality=192) for i in range(1000)]
        result = _downsample(pts, 100)
        # LTTB always includes first and last
        assert result[0] == pts[0]
        assert result[-1] == pts[-1]
        assert len(result) == 100

    def test_preserves_peaks(self):
        """LTTB must keep the spike value — naive thinning would drop it."""
        pts = [RawReading(timestamp=_ts(i), value=1.0, quality=192) for i in range(200)]
        pts[100] = RawReading(timestamp=_ts(100), value=9999.0, quality=192)
        result = _downsample(pts, 50)
        values = [p.value for p in result]
        assert 9999.0 in values


# --------------------------------------------------------------------------- #
# get_raw
# --------------------------------------------------------------------------- #

class TestGetRaw:
    @pytest.mark.asyncio
    async def test_returns_grouped_by_signal(self, db_session):
        svc = SignalService(session=db_session)
        readings = [
            _reading("Ramp1", 10.0, 0),
            _reading("Ramp1", 12.0, 1),
            _reading("Ramp2", 5.0, 0),
        ]

        with (
            patch.object(svc._machine_repo, "get_or_raise", AsyncMock(return_value=object())),
            patch.object(svc._sig_def_repo, "get_names_for_machine", AsyncMock(return_value=["Ramp1", "Ramp2"])),
            patch.object(svc._repo, "get_raw", AsyncMock(return_value=readings)),
            patch.object(svc._sig_def_repo, "get_by_machine", AsyncMock(return_value=[])),
        ):
            result = await svc.get_raw("M01", ["Ramp1", "Ramp2"], "1h", None, True)

        assert len(result) == 2
        ramp1 = next(r for r in result if r.signal_name == "Ramp1")
        assert len(ramp1.readings) == 2
        ramp2 = next(r for r in result if r.signal_name == "Ramp2")
        assert len(ramp2.readings) == 1

    @pytest.mark.asyncio
    async def test_raises_400_for_unknown_signal(self, db_session):
        svc = SignalService(session=db_session)
        with (
            patch.object(svc._machine_repo, "get_or_raise", AsyncMock(return_value=object())),
            patch.object(svc._sig_def_repo, "get_names_for_machine", AsyncMock(return_value=["Ramp1"])),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await svc.get_raw("M01", ["Ramp1", "UnknownSignal"], "1h", None, True)
        assert exc_info.value.status_code == 400
        assert "UnknownSignal" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_applies_downsampling_when_resolution_set(self, db_session):
        svc = SignalService(session=db_session)
        # 500 readings, ask for 50
        readings = [_reading("Ramp1", float(i), i) for i in range(500)]

        with (
            patch.object(svc._machine_repo, "get_or_raise", AsyncMock(return_value=object())),
            patch.object(svc._sig_def_repo, "get_names_for_machine", AsyncMock(return_value=[])),
            patch.object(svc._repo, "get_raw", AsyncMock(return_value=readings)),
            patch.object(svc._sig_def_repo, "get_by_machine", AsyncMock(return_value=[])),
        ):
            result = await svc.get_raw("M01", ["Ramp1"], "1h", 50, True)

        assert len(result[0].readings) == 50


# --------------------------------------------------------------------------- #
# get_latest — threshold checks
# --------------------------------------------------------------------------- #

class TestGetLatest:
    @pytest.mark.asyncio
    async def test_flags_alarm_when_value_exceeds_high(self, db_session):
        from app.models.machine import Machine, SignalDefinition

        svc = SignalService(session=db_session)

        machine = Machine(id="M01", name="M01", status="online")
        machine.signal_definitions = []

        sig_def = SignalDefinition(
            id=1,
            machine_id="M01",
            signal_name="Temperature",
            unit="°C",
            alarm_high=100.0,
            alarm_low=None,
            warn_high=None,
            warn_low=None,
        )

        reading = _reading("Temperature", 150.0)  # exceeds alarm_high

        with (
            patch.object(svc._machine_repo, "get_or_raise", AsyncMock(return_value=machine)),
            patch.object(svc._repo, "get_latest_per_signal", AsyncMock(return_value=[reading])),
            patch.object(svc._sig_def_repo, "get_by_machine", AsyncMock(return_value=[sig_def])),
        ):
            result = await svc.get_latest("M01")

        assert result.readings[0].is_alarm is True
        assert result.readings[0].is_warning is False
