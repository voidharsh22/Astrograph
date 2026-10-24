"""Graph endpoints — serves 3D galaxy payloads."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.graph_schema import AstralGraph
from app.schemas.requests import RepoAnalyzeRequest
from app.services.cartographer import build_graph
from app.services.ingestor import cleanup_clone, ingest_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])

# ---------------------------------------------------------------------------
# Demo endpoint (Phase 1)
# ---------------------------------------------------------------------------

_DEMO_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "demo_galaxy.json"
_demo_graph: AstralGraph | None = None


def _load_demo_graph() -> AstralGraph:
    """Lazily load and validate the demo galaxy JSON against our Pydantic schema."""
    global _demo_graph  # noqa: PLW0603
    if _demo_graph is None:
        raw = json.loads(_DEMO_DATA_PATH.read_text(encoding="utf-8"))
        _demo_graph = AstralGraph.model_validate(raw)
    return _demo_graph


@router.get(
    "/demo",
    response_model=AstralGraph,
    summary="Demo galaxy payload",
    description=(
        "Returns a hardcoded sample 3D galaxy graph representing a fictitious "
        "repository. Use this endpoint to develop and test the Three.js frontend "
        "while the real ingestion pipeline is being built."
    ),
)
async def get_demo_graph() -> AstralGraph:
    return _load_demo_graph()


# ---------------------------------------------------------------------------
# Analyze endpoint (Phase 2)
# ---------------------------------------------------------------------------

@router.post(
    "/analyze",
    response_model=AstralGraph,
    summary="Analyze a GitHub repository",
    description=(
        "Accepts a public GitHub repository URL, shallow-clones it, parses the "
        "source code to extract structural nodes and dependency edges, computes "
        "graph metrics (PageRank, centrality, community clustering), and returns "
        "the full 3D galaxy graph payload."
    ),
    responses={
        400: {"description": "Invalid repository URL"},
        502: {"description": "Failed to clone or parse repository"},
    },
)
async def analyze_repository(request: RepoAnalyzeRequest) -> AstralGraph:
    """Clone, parse, and graph-ify a GitHub repository."""
    clone_path = None
    try:
        # Step 1: Ingest (clone + metadata)
        logger.info("Ingesting repository: %s (branch: %s)", request.repo_url, request.branch)
        repo_data = await ingest_repository(request.repo_url, request.branch)
        clone_path = repo_data.clone_path

        logger.info(
            "Ingested %d files from %s", len(repo_data.files), repo_data.repo_name
        )

        # Step 2: Build graph
        graph = await build_graph(repo_data, include_ai=request.include_ai_summary)

        from app.services.graph_store import GraphStore, set_active_graph_store

        set_active_graph_store(GraphStore(graph))

        logger.info(
            "Built graph: %d nodes, %d edges (%.1fms)",
            len(graph.nodes),
            len(graph.edges),
            graph.metadata.analysis_duration_ms or 0,
        )

        return graph

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to analyze repository: %s", request.repo_url)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to analyze repository: {exc}",
        ) from exc
    finally:
        # Always clean up the clone
        if clone_path:
            cleanup_clone(clone_path)
