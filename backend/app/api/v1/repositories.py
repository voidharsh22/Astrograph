"""
Repositories API router — asynchronous ingestion, repository listing, graph retrieval,
dependency traversal, and architectural impact analysis.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.schemas.graph_schema import AstralGraph
from app.schemas.requests import RepoAnalyzeRequest
from app.services.downloader import extract_github_owner_and_repo
from app.services.graph_queries import compute_impact_analysis, get_dependencies_for_node
from app.services.graph_store import get_active_graph_store
from app.services.indexing_service import run_indexing_pipeline
from app.storage.repository_store import (
    create_job,
    create_or_get_repository,
    get_repository,
    list_repositories,
    load_graph_artifact,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Repository for Background Indexing",
    description="Asynchronously queues a public GitHub repository for secure download, Tree-sitter parsing, and 3D galaxy graph calculation.",
)
async def submit_repository(
    request: RepoAnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Queue a repository for asynchronous indexing and 3D celestial mapping."""
    try:
        owner, repo_name = extract_github_owner_and_repo(request.repo_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo = create_or_get_repository(
        url=request.repo_url,
        owner=owner,
        name=repo_name,
        branch=request.branch,
    )
    repo_id = repo["id"]
    job = create_job(repo_id)
    job_id = job["id"]

    background_tasks.add_task(
        run_indexing_pipeline,
        repo_id=repo_id,
        job_id=job_id,
        url=request.repo_url,
        branch=request.branch,
    )

    return {
        "repository_id": repo_id,
        "job_id": job_id,
        "status": "queued",
        "message": "Repository indexing queued. Connect to /api/v1/jobs/{job_id} to poll progress.",
    }


@router.get(
    "",
    summary="List Repositories",
    description="Retrieve all indexed repositories with pagination.",
)
async def list_all_repositories(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """List indexed repositories."""
    return list_repositories(limit=limit, offset=offset)


@router.get(
    "/{repo_id}",
    summary="Get Repository Details",
    description="Retrieve status and metadata for a specific repository.",
)
async def get_repository_details(repo_id: str) -> dict[str, Any]:
    """Retrieve repository details by ID."""
    repo = get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found")
    return repo


@router.get(
    "/{repo_id}/graph",
    response_model=AstralGraph,
    summary="Get 3D Galaxy Graph",
    description="Retrieve the complete 3D AstralGraph payload formatted for Three.js rendering.",
)
async def get_repository_graph(repo_id: str) -> AstralGraph:
    """Retrieve 3D celestial graph for an indexed repository."""
    graph = load_graph_artifact(repo_id)
    if graph is not None:
        set_active_graph_store(get_active_graph_store().__class__(graph))
        return graph

    active_store = get_active_graph_store()
    if active_store and active_store.graph:
        return active_store.graph

    raise HTTPException(
        status_code=404,
        detail=f"3D graph for repository '{repo_id}' is not yet indexed or ready",
    )


@router.get(
    "/{repo_id}/dependencies",
    summary="Query Node Dependencies",
    description="Traverse incoming or outgoing dependencies for any given node up to specified depth.",
)
async def query_node_dependencies(
    repo_id: str,
    node_id: str = Query(..., description="Unique node ID to inspect"),
    direction: str = Query("outgoing", pattern="^(outgoing|incoming|both)$"),
    depth: int = Query(1, ge=1, le=5),
) -> dict[str, Any]:
    """Query dependencies for a node in the repository graph."""
    graph = load_graph_artifact(repo_id) or get_active_graph_store().graph
    return get_dependencies_for_node(graph, node_id=node_id, direction=direction, depth=depth)


@router.get(
    "/{repo_id}/impact",
    summary="Architectural Blast Radius Impact Analysis",
    description="Calculate all downstream callers, subclasses, and importers affected if a node is modified.",
)
async def query_impact_analysis(
    repo_id: str,
    node_id: str = Query(..., description="Target node ID to analyze"),
    max_depth: int = Query(3, ge=1, le=10),
) -> dict[str, Any]:
    """Compute architectural impact analysis for a node."""
    graph = load_graph_artifact(repo_id) or get_active_graph_store().graph
    return compute_impact_analysis(graph, target_node_id=node_id, max_depth=max_depth)
