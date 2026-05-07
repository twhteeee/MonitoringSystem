"""
Pydantic v2 schemas for signal reading endpoints.

Three response shapes:
  RawReading        — individual timestamped value
  AggregatedReading — min/avg/max per time bucket (for zoomed-out views)
  LatestReading     — most recent value per signal (for live dashboard tiles)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Query parameters (shared)
# --------------------------------------------------------------------------- #

TimeRange = Literal["15m", "1h", "6h", "24h", "7d", "30d"]

RANGE_HOURS: dict[TimeRange, float] = {
    "15m": 0.25,
    "1h":  1,
    "6h":  6,
    "24h": 24,
    "7d":  168,
    "30d": 720,
}


class SignalQueryParams(BaseModel):
    """Common query parameters for time-series endpoints."""
    signals: list[str] = Field(
        ...,
        description="One or more signal names to query (e.g. Ramp1, Ramp2).",
        min_length=1,
        max_length=20,
    )
    range: TimeRange = Field(
        "1h",
        description="Time window. Determines how far back from now to fetch.",
    )
    resolution: int | None = Field(
        None,
        ge=10,
        le=10000,
        description=(
            "Max number of data points to return per signal. "
            "Server-side downsampling is applied when actual rows exceed this. "
            "Omit to return all raw rows."
        ),
    )
    quality_filter: bool = Field(
        True,
        description="When True, exclude readings with OPC quality != 192 (Good).",
    )


# --------------------------------------------------------------------------- #
# Individual reading
# --------------------------------------------------------------------------- #

class RawReading(BaseModel):
    timestamp: datetime
    value: float
    quality: int = 192

    model_config = {"from_attributes": True}


class SignalData(BaseModel):
    """A single signal's readings within a query window."""
    machine_id: str
    signal_name: str
    unit: str | None = None
    readings: list[RawReading]


# --------------------------------------------------------------------------- #
# Aggregated reading (used for long time ranges)
# --------------------------------------------------------------------------- #

class AggregatedReading(BaseModel):
    bucket_start: datetime
    min_value: float
    avg_value: float
    max_value: float
    sample_count: int


class AggregatedSignalData(BaseModel):
    machine_id: str
    signal_name: str
    unit: str | None = None
    bucket_minutes: int
    readings: list[AggregatedReading]


# --------------------------------------------------------------------------- #
# Latest value (for live tiles)
# --------------------------------------------------------------------------- #

class LatestReading(BaseModel):
    machine_id: str
    signal_name: str
    value: float
    quality: int
    timestamp: datetime
    unit: str | None = None
    # Threshold flags — set by service layer against SignalDefinition
    is_alarm: bool = False
    is_warning: bool = False

    model_config = {"from_attributes": True}


class MachineLatestReadings(BaseModel):
    machine_id: str
    machine_name: str
    readings: list[LatestReading]


# --------------------------------------------------------------------------- #
# Multi-machine response (for /signals/multi endpoint)
# --------------------------------------------------------------------------- #

class MultiMachineSignalResponse(BaseModel):
    machines: list[SignalData]
    queried_at: datetime
    range: TimeRange
    total_points: int
