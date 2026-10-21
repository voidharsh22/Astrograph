"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns the current server status, version, and UTC timestamp.",
)
async def health_check() -> HealthResponse:
    return HealthResponse(version=settings.app_version)
