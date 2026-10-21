"""Analysis endpoints — Galaxy cluster summarization and workflow tracing."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.agents.cluster_agent import summarize_galaxy_clusters
from app.agents.workflow_tracing_agent import trace_codebase_workflows
from app.schemas.requests import (
    ClusterAnalyzeRequest,
    ClusterAnalyzeResponse,
    WorkflowAnalyzeRequest,
    WorkflowAnalyzeResponse,
)
from app.services.graph_store import get_active_graph_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post(
    "/clusters",
    response_model=ClusterAnalyzeResponse,
    summary="Synthesize Galaxy Module Summaries",
    description=(
        "Batch processes the active repository's Louvain community clusters. "
        "Aggregates the top 3-5 central nodes (PageRank) per cluster and prompts "
        "Gemini to synthesize high-level 'Galaxy Summaries' that are displayed "
        "when zooming out in the 3D frontend."
    ),
    responses={
        500: {"description": "Failed to synthesize cluster summaries"},
    },
)
async def analyze_clusters(
    request: ClusterAnalyzeRequest | None = None,
) -> ClusterAnalyzeResponse:
    """Run the Galaxy cluster summarization LangGraph agent."""
    try:
        store = get_active_graph_store()
        summaries = await summarize_galaxy_clusters(store.graph)
        return ClusterAnalyzeResponse(
            total_clusters=len(summaries),
            cluster_summaries=summaries,
        )
    except Exception as exc:
        logger.exception("Failed to synthesize cluster summaries: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to synthesize cluster summaries: {exc}",
        ) from exc


@router.post(
    "/workflows",
    response_model=WorkflowAnalyzeResponse,
    summary="Trace Execution Workflows ('Glowing Pulses')",
    description=(
        "Discovers application entry points (routers, page components, main.py) "
        "and traces logical execution pathways down to database/model layers. "
        "Returns ordered node and edge IDs to animate glowing pulses along the pathways."
    ),
    responses={
        500: {"description": "Failed to trace workflows"},
    },
)
async def analyze_workflows(
    request: WorkflowAnalyzeRequest | None = None,
) -> WorkflowAnalyzeResponse:
    """Run the execution workflow tracing LangGraph agent."""
    try:
        store = get_active_graph_store()
        max_wf = request.max_workflows if request else 3

        # Run extraction
        workflows = await trace_codebase_workflows(
            graph=store.graph,
            max_workflows=max_wf,
        )

        return WorkflowAnalyzeResponse(
            status="completed",
            total_workflows=len(workflows),
            workflows=workflows,
        )
    except Exception as exc:
        logger.exception("Failed to trace workflows: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trace workflows: {exc}",
        ) from exc
