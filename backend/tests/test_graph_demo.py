"""Tests for GET /api/v1/graph/demo."""

from __future__ import annotations

from httpx import AsyncClient

from app.schemas.graph_schema import AstralGraph


async def test_demo_graph_returns_200(client: AsyncClient) -> None:
    """Demo graph endpoint returns 200."""
    resp = await client.get("/api/v1/graph/demo")
    assert resp.status_code == 200


async def test_demo_graph_validates_against_schema(client: AsyncClient) -> None:
    """The full response validates against the AstralGraph Pydantic model."""
    resp = await client.get("/api/v1/graph/demo")
    graph = AstralGraph.model_validate(resp.json())

    assert graph.repo_name == "cosmic-weather-api"
    assert graph.branch == "main"
    assert graph.commit_sha is not None


async def test_demo_graph_has_expected_counts(client: AsyncClient) -> None:
    """Demo graph contains the expected number of nodes, edges, and workflows."""
    resp = await client.get("/api/v1/graph/demo")
    graph = AstralGraph.model_validate(resp.json())

    assert len(graph.nodes) == 15
    assert len(graph.edges) == 24
    assert len(graph.workflows) == 2


async def test_demo_graph_node_types(client: AsyncClient) -> None:
    """Demo graph contains all four node types."""
    resp = await client.get("/api/v1/graph/demo")
    graph = AstralGraph.model_validate(resp.json())

    types_present = {node.type.value for node in graph.nodes}
    assert types_present == {"directory", "file", "function", "class"}


async def test_demo_graph_edge_relations(client: AsyncClient) -> None:
    """Demo graph contains at least imports, calls, and contains relations."""
    resp = await client.get("/api/v1/graph/demo")
    graph = AstralGraph.model_validate(resp.json())

    relations = {edge.relation.value for edge in graph.edges}
    assert "imports" in relations
    assert "calls" in relations
    assert "contains" in relations


async def test_demo_graph_workflow_references_valid_nodes(client: AsyncClient) -> None:
    """Every node ID referenced in workflows exists in the nodes list."""
    resp = await client.get("/api/v1/graph/demo")
    graph = AstralGraph.model_validate(resp.json())

    node_ids = {node.id for node in graph.nodes}
    for wf in graph.workflows:
        for nid in wf.ordered_node_ids:
            assert nid in node_ids, f"Workflow '{wf.name}' references unknown node '{nid}'"


async def test_demo_graph_workflow_references_valid_edges(client: AsyncClient) -> None:
    """Every edge ID referenced in workflows exists in the edges list."""
    resp = await client.get("/api/v1/graph/demo")
    graph = AstralGraph.model_validate(resp.json())

    edge_ids = {edge.id for edge in graph.edges}
    for wf in graph.workflows:
        for eid in wf.edge_ids:
            assert eid in edge_ids, f"Workflow '{wf.name}' references unknown edge '{eid}'"
