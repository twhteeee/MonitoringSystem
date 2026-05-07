"""
Signal data endpoints — /api/v1/signals

GET /signals/{machine_id}/raw
    Return raw time-series readings for one or more signals.
    Supports optional client-driven downsampling via ?resolution=N.

GET /signals/{machine_id}/aggregated/{signal_name}
    Return server-side bucketed min/avg/max for a single signal.
    Recommended for 7d / 30d ranges.

GET /signals/{machine_id}/latest
    Return the most recent reading for every signal of a machine.
    Used by the live dashboard tiles.

POST /signals/multi/raw
    Cross-machine query — fetches the same signals from multiple
    machines in a single request (used by comparison views).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_signal_service
from app.core.security import TokenPayload, get_viewer
from app.schemas.signal import (
    AggregatedSignalData,
    MachineLatestReadings,
    MultiMachineSignalResponse,
    SignalData,
    TimeRange,
)
from app.services.signal_service import SignalService

router = APIRouter(prefix="/signals", tags=["Signals"])


# --------------------------------------------------------------------------- #
# Raw
# --------------------------------------------------------------------------- #

@router.get(
    "/{machine_id}/raw",
    response_model=list[SignalData],
    summary="Raw time-series readings for one or more signals",
    description=(
        "Returns individual timestamped readings. "
        "For ranges ≥ 6h consider using /aggregated instead to avoid "
        "large response payloads."
    ),
)
async def get_raw_signals(
    machine_id: str,
    signals: list[str] = Query(
        ...,
        description="Signal names to query. Repeat the param for multiple: ?signals=Ramp1&signals=Ramp2",
        min_length=1,
    ),
    range: TimeRange = Query("1h", description="Time window"),
    resolution: int | None = Query(
        None,
        ge=10,
        le=10000,
        description="Max points per signal. Applies LTTB downsampling when exceeded.",
    ),
    quality_filter: bool = Query(True, description="Exclude OPC bad-quality readings"),
    _user: TokenPayload = Depends(get_viewer),
    svc: SignalService = Depends(get_signal_service),
) -> list[SignalData]:
    return await svc.get_raw(
        machine_id=machine_id,
        signals=signals,
        range_=range,
        resolution=resolution,
        quality_filter=quality_filter,
    )


# --------------------------------------------------------------------------- #
# Aggregated
# --------------------------------------------------------------------------- #

@router.get(
    "/{machine_id}/aggregated/{signal_name}",
    response_model=AggregatedSignalData,
    summary="Bucketed min/avg/max for a single signal",
    description=(
        "Uses server-side T-SQL time-bucketing. "
        "Bucket size is auto-selected to produce ~500 data points for the range. "
        "Ideal for 7d and 30d views."
    ),
)
async def get_aggregated_signal(
    machine_id: str,
    signal_name: str,
    range: TimeRange = Query("24h"),
    _user: TokenPayload = Depends(get_viewer),
    svc: SignalService = Depends(get_signal_service),
) -> AggregatedSignalData:
    return await svc.get_aggregated(
        machine_id=machine_id,
        signal_name=signal_name,
        range_=range,
    )


# --------------------------------------------------------------------------- #
# Latest (live tiles)
# --------------------------------------------------------------------------- #

@router.get(
    "/{machine_id}/latest",
    response_model=MachineLatestReadings,
    summary="Most recent value per signal — for live dashboard tiles",
    description=(
        "Returns the single latest reading for each signal. "
        "Response is cached with a very short TTL (5 s) to avoid "
        "hammering the database from multiple concurrent dashboard clients."
    ),
)
async def get_latest_readings(
    machine_id: str,
    signals: list[str] | None = Query(
        None,
        description="Filter to specific signals. Omit to get all signals.",
    ),
    _user: TokenPayload = Depends(get_viewer),
    svc: SignalService = Depends(get_signal_service),
) -> MachineLatestReadings:
    return await svc.get_latest(machine_id=machine_id, signals=signals)


# --------------------------------------------------------------------------- #
# Multi-machine
# --------------------------------------------------------------------------- #

class MultiMachineRequest(object):
    pass


from pydantic import BaseModel, Field


class MultiMachineRequestBody(BaseModel):
    machine_ids: list[str] = Field(..., min_length=1, max_length=20)
    signals: list[str] = Field(..., min_length=1, max_length=20)
    range: TimeRange = "1h"
    resolution: int | None = Field(None, ge=10, le=10000)
    quality_filter: bool = True


@router.post(
    "/multi/raw",
    response_model=MultiMachineSignalResponse,
    summary="Cross-machine raw signal query",
    description=(
        "Fetch the same set of signals from multiple machines in one call. "
        "Used by the comparison and overview views in the frontend."
    ),
)
async def get_multi_machine_signals(
    body: MultiMachineRequestBody,
    _user: TokenPayload = Depends(get_viewer),
    svc: SignalService = Depends(get_signal_service),
) -> MultiMachineSignalResponse:
    return await svc.get_multi_machine(
        machine_ids=body.machine_ids,
        signals=body.signals,
        range_=body.range,
        resolution=body.resolution,
        quality_filter=body.quality_filter,
    )
