"""Shared response envelopes and pagination schemas."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    request_id: str
    errors: list[ErrorDetail]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str
    db: str = "ok"
    cache: str = "ok"
