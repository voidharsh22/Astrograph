"""Request models for the Astral Cartographer API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.graph_schema import Workflow
from app.services.ingestor import validate_github_url


class RepoAnalyzeRequest(BaseModel):
    """Request body for POST /api/v1/graph/analyze."""

    repo_url: str = Field(
        ...,
        description="Public GitHub repository URL (e.g. https://github.com/owner/repo)",
        examples=["https://github.com/pallets/flask"],
    )
    branch: str = Field(
        "main",
        description="Branch to analyze (default: main)",
        examples=["main", "develop", "master"],
    )
    include_ai_summary: bool = Field(
        True,
        description="When true, enrich the graph with AI-generated summaries and workflow detection.",
    )

    @field_validator("repo_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not validate_github_url(v):
            raise ValueError(
                "Must be a valid GitHub repository URL "
                "(e.g. https://github.com/owner/repo)"
            )
        return v


class ClusterAnalyzeRequest(BaseModel):
    """Request body for POST /api/v1/analyze/clusters."""

    repo_url: str | None = Field(
        None,
        description="Optional repository URL. If omitted, uses the active in-memory graph.",
    )


class ClusterAnalyzeResponse(BaseModel):
    """Response body for POST /api/v1/analyze/clusters."""

    total_clusters: int = Field(..., description="Total community clusters analyzed.")
    cluster_summaries: dict[int, str] = Field(
        ...,
        description="Synthesized high-level Galaxy summaries keyed by Louvain cluster ID.",
    )


class WorkflowAnalyzeRequest(BaseModel):
    """Request body for POST /api/v1/analyze/workflows."""

    repo_url: str | None = Field(
        None,
        description="Optional repository URL. If omitted, uses the active in-memory graph.",
    )
    max_workflows: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum number of execution workflows to trace.",
    )


class WorkflowAnalyzeResponse(BaseModel):
    """Response body for POST /api/v1/analyze/workflows."""

    status: str = Field("completed", description="Task execution status.")
    total_workflows: int = Field(..., description="Number of detected workflows.")
    workflows: list[Workflow] = Field(..., description="List of detected Workflow objects.")

