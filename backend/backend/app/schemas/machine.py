"""
Pydantic v2 schemas for Machine and SignalDefinition endpoints.

Separating schemas from ORM models ensures the API contract is
explicit and never accidentally leaks internal fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------- #
# Signal definition
# --------------------------------------------------------------------------- #

class SignalDefinitionBase(BaseModel):
    signal_name: str = Field(..., min_length=1, max_length=100, examples=["Ramp1"])
    unit: str | None = Field(None, max_length=50, examples=["°C"])
    description: str | None = Field(None, max_length=255)
    min_value: float | None = None
    max_value: float | None = None
    warn_low: float | None = None
    warn_high: float | None = None
    alarm_low: float | None = None
    alarm_high: float | None = None


class SignalDefinitionCreate(SignalDefinitionBase):
    pass


class SignalDefinitionUpdate(BaseModel):
    unit: str | None = None
    description: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    warn_low: float | None = None
    warn_high: float | None = None
    alarm_low: float | None = None
    alarm_high: float | None = None


class SignalDefinitionResponse(SignalDefinitionBase):
    id: int
    machine_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------- #
# Machine
# --------------------------------------------------------------------------- #

MachineStatus = Literal["online", "warning", "offline", "maintenance", "unknown"]


class MachineBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, examples=["Machine 01"])
    description: str | None = Field(None, max_length=255)
    location: str | None = Field(None, max_length=100, examples=["Line A, Bay 3"])
    status: MachineStatus = "unknown"


class MachineCreate(MachineBase):
    id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_\-]+$",
        examples=["M01"],
    )
    signal_definitions: list[SignalDefinitionCreate] = Field(default_factory=list)


class MachineUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    location: str | None = None
    status: MachineStatus | None = None


class MachineResponse(MachineBase):
    id: str
    created_at: datetime
    updated_at: datetime
    signal_definitions: list[SignalDefinitionResponse] = []

    model_config = {"from_attributes": True}


class MachineSummary(BaseModel):
    """Lightweight response used in list endpoints."""
    id: str
    name: str
    location: str | None
    status: MachineStatus
    signal_count: int = 0

    model_config = {"from_attributes": True}
