"""Shared response models and error envelopes."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response schema for the /health endpoint."""

    status: str = "ok"
    version: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorDetail(BaseModel):
    """Standardized error detail for API error responses."""

    code: str
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    """Standardized error envelope."""

    error: ErrorDetail
