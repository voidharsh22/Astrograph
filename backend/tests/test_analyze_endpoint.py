"""Tests for POST /api/v1/graph/analyze endpoint."""

from __future__ import annotations

from httpx import AsyncClient

from app.schemas.graph_schema import AstralGraph


async def test_analyze_rejects_invalid_url(client: AsyncClient) -> None:
    """Analyze endpoint returns 422 for a non-GitHub URL."""
    resp = await client.post(
        "/api/v1/graph/analyze",
        json={"repo_url": "https://gitlab.com/owner/repo"},
    )
    assert resp.status_code == 422


async def test_analyze_rejects_empty_url(client: AsyncClient) -> None:
    """Analyze endpoint returns 422 for empty URL."""
    resp = await client.post(
        "/api/v1/graph/analyze",
        json={"repo_url": ""},
    )
    assert resp.status_code == 422


async def test_analyze_rejects_missing_url(client: AsyncClient) -> None:
    """Analyze endpoint returns 422 when repo_url is missing."""
    resp = await client.post(
        "/api/v1/graph/analyze",
        json={},
    )
    assert resp.status_code == 422


async def test_analyze_accepts_valid_github_url_format(client: AsyncClient) -> None:
    """
    Verify the endpoint accepts a well-formed GitHub URL.

    NOTE: This test intentionally uses a non-existent repo to avoid
    network dependency in CI. The 502 (clone failure) confirms the
    URL validation passed and the pipeline attempted to clone.
    """
    resp = await client.post(
        "/api/v1/graph/analyze",
        json={"repo_url": "https://github.com/nonexistent-owner-xyz/nonexistent-repo-xyz"},
    )
    # URL validation passed (would be 422 otherwise), clone failed as expected
    assert resp.status_code == 502
