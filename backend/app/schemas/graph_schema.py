"""
3D Graph Serialization Contract for Astral Cartographer.

This is the **core schema contract** between the backend and the 3D frontend.
Every processed repository is serialized into an `AstralGraph` that the
Three.js/React-Three-Fiber frontend consumes directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class NodeType(str, Enum):
    """Type of structural element in the codebase graph."""

    DIRECTORY = "directory"
    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"


class EdgeRelation(str, Enum):
    """Semantic relationship between two nodes."""

    IMPORTS = "imports"
    CALLS = "calls"
    CONTAINS = "contains"
    INHERITS = "inherits"


# ---------------------------------------------------------------------------
# Node sub-models
# ---------------------------------------------------------------------------

class NodeMetrics(BaseModel):
    """Computed metrics that drive visual properties (size, brightness, etc.)."""

    loc: int = Field(0, ge=0, description="Lines of code")
    centrality: float = Field(
        0.0, ge=0.0, le=1.0, description="PageRank / degree centrality [0-1]"
    )
    complexity: float = Field(
        0.0, ge=0.0, description="Cyclomatic or cognitive complexity score"
    )


class PositionHint(BaseModel):
    """Layout hints consumed by the 3D force-graph engine."""

    cluster_id: int = Field(
        0, ge=0, description="Community / cluster ID from Louvain detection"
    )
    depth: int = Field(
        0, ge=0, description="Depth in the directory tree (root = 0)"
    )


# ---------------------------------------------------------------------------
# Primary graph elements
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    """A single node in the codebase galaxy."""

    id: str = Field(..., description="Unique deterministic ID (e.g. 'src/utils.py::parse_config')")
    label: str = Field(..., description="Human-friendly display name")
    type: NodeType
    language: str | None = Field(None, description="Programming language (e.g. 'python', 'typescript')")
    path: str = Field(..., description="Relative path from repo root")
    metrics: NodeMetrics = Field(default_factory=NodeMetrics)
    position_hint: PositionHint = Field(default_factory=PositionHint)
    ai_summary: str | None = Field(None, description="AI-generated 1-2 sentence summary (Phase 3)")


class GraphEdge(BaseModel):
    """A directed edge between two nodes."""

    id: str = Field(..., description="Unique edge ID (e.g. 'e-src/main.py->src/utils.py-imports')")
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    relation: EdgeRelation
    weight: float = Field(1.0, ge=0.0, description="Edge weight / strength")


class Workflow(BaseModel):
    """
    A named execution pathway through the codebase.

    The 3D frontend animates glowing pulses along these paths
    to illustrate request lifecycles, data pipelines, etc.
    """

    id: str = Field(..., description="Unique workflow ID")
    name: str = Field(..., description="Human-readable workflow name")
    description: str = Field("", description="What this workflow represents")
    ordered_node_ids: list[str] = Field(
        default_factory=list,
        description="Node IDs in execution order",
    )
    edge_ids: list[str] = Field(
        default_factory=list,
        description="Edge IDs traversed by this workflow",
    )


# ---------------------------------------------------------------------------
# Top-level graph envelope
# ---------------------------------------------------------------------------

class GraphMetadata(BaseModel):
    """Aggregate statistics about the analyzed repository."""

    total_files: int = 0
    total_functions: int = 0
    total_classes: int = 0
    languages: list[str] = Field(default_factory=list)
    analysis_duration_ms: float | None = None
    cluster_summaries: dict[int, str] = Field(
        default_factory=dict,
        description="Galaxy module summaries mapped by Louvain cluster ID.",
    )


class AstralGraph(BaseModel):
    """
    The complete 3D graph payload for a repository.

    This is the top-level JSON object returned by every graph endpoint.
    """

    repo_url: str = Field(..., description="Source repository URL")
    repo_name: str = Field(..., description="Repository display name")
    branch: str = Field("main", description="Analyzed branch")
    commit_sha: str | None = Field(None, description="HEAD commit SHA at analysis time")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    workflows: list[Workflow] = Field(default_factory=list)
    metadata: GraphMetadata = Field(default_factory=GraphMetadata)
