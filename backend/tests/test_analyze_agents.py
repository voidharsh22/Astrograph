"""Tests for Cluster Summarization, Workflow Tracing Agents, and Analysis Endpoints (Artifact 3)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.agents.cluster_agent import (
    ClusterAgentState,
    cluster_agent_app,
    summarize_galaxy_clusters,
)
from app.agents.workflow_tracing_agent import (
    WorkflowTraceState,
    trace_codebase_workflows,
    workflow_tracing_app,
)
from app.schemas.graph_schema import Workflow
from app.services.graph_store import get_active_graph_store


@pytest.mark.asyncio
async def test_cluster_summarization_agent_execution():
    """Verify Feature B: Louvain community cluster summarization via LangGraph."""
    store = get_active_graph_store()
    initial_state: ClusterAgentState = {
        "graph": store.graph,
        "clusters_data": {},
        "cluster_summaries": {},
    }

    result = await cluster_agent_app.ainvoke(initial_state)

    assert "cluster_summaries" in result
    summaries = result["cluster_summaries"]
    assert isinstance(summaries, dict)
    assert len(summaries) > 0
    # Every cluster ID should have a summary string
    for cid, summary in summaries.items():
        assert isinstance(cid, int)
        assert isinstance(summary, str)
        assert len(summary) > 0

    # Ensure store graph was mutated
    assert len(store.graph.metadata.cluster_summaries) > 0


@pytest.mark.asyncio
async def test_workflow_tracing_agent_execution():
    """Verify Feature C: Execution workflow tracing via LangGraph."""
    store = get_active_graph_store()
    initial_state: WorkflowTraceState = {
        "graph": store.graph,
        "max_workflows": 3,
        "entry_points": [],
        "adjacency": {},
        "raw_paths": [],
        "traced_workflows": [],
    }

    result = await workflow_tracing_app.ainvoke(initial_state)

    assert "traced_workflows" in result
    workflows = result["traced_workflows"]
    assert isinstance(workflows, list)
    assert len(workflows) > 0

    first_wf = workflows[0]
    assert isinstance(first_wf, Workflow)
    assert first_wf.id
    assert first_wf.name
    assert first_wf.description
    assert len(first_wf.ordered_node_ids) >= 2


async def test_post_analyze_clusters_endpoint(client: AsyncClient) -> None:
    """Verify POST /api/v1/analyze/clusters returns 200 with cluster summaries."""
    resp = await client.post("/api/v1/analyze/clusters", json={})
    assert resp.status_code == 200

    data = resp.json()
    assert "total_clusters" in data
    assert data["total_clusters"] > 0
    assert "cluster_summaries" in data
    assert isinstance(data["cluster_summaries"], dict)


async def test_post_analyze_workflows_endpoint(client: AsyncClient) -> None:
    """Verify POST /api/v1/analyze/workflows returns 200 with traced workflow objects."""
    resp = await client.post("/api/v1/analyze/workflows", json={"max_workflows": 3})
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "completed"
    assert "total_workflows" in data
    assert data["total_workflows"] > 0
    assert "workflows" in data
    assert len(data["workflows"]) > 0

    wf = data["workflows"][0]
    assert "id" in wf
    assert "name" in wf
    assert "ordered_node_ids" in wf
    assert "edge_ids" in wf


async def test_root_redirect_to_docs(client: AsyncClient) -> None:
    """Verify GET / redirects to /docs."""
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/docs"
