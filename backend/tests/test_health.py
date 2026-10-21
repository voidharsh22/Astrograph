"""Tests for GET /api/v1/health."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_200(client: AsyncClient) -> None:
    """Health endpoint returns 200 with correct shape."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "timestamp" in body


async def test_health_version_matches_config(client: AsyncClient) -> None:
    """Health endpoint version matches the app config."""
    from app.config import settings

    resp = await client.get("/api/v1/health")
    body = resp.json()
    assert body["version"] == settings.app_version
