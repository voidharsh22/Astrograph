"""Tests for Pydantic schema validation and serialization."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.graph_schema import (
    AstralGraph,
    EdgeRelation,
    GraphEdge,
    GraphNode,
    NodeMetrics,
    NodeType,
    PositionHint,
    Workflow,
)


class TestNodeMetrics:
    """NodeMetrics validation tests."""

    def test_defaults(self) -> None:
        m = NodeMetrics()
        assert m.loc == 0
        assert m.centrality == 0.0
        assert m.complexity == 0.0

    def test_valid_values(self) -> None:
        m = NodeMetrics(loc=150, centrality=0.85, complexity=12.3)
        assert m.loc == 150
        assert m.centrality == 0.85

    def test_centrality_out_of_range_rejects(self) -> None:
        with pytest.raises(ValidationError):
            NodeMetrics(centrality=1.5)

    def test_negative_loc_rejects(self) -> None:
        with pytest.raises(ValidationError):
            NodeMetrics(loc=-1)


class TestGraphNode:
    """GraphNode validation tests."""

    def test_minimal_node(self) -> None:
        node = GraphNode(id="test-1", label="test", type=NodeType.FILE, path="src/test.py")
        assert node.language is None
        assert node.ai_summary is None
        assert node.metrics.loc == 0

    def test_full_node(self) -> None:
        node = GraphNode(
            id="func::main.py::run",
            label="run()",
            type=NodeType.FUNCTION,
            language="python",
            path="main.py",
            metrics=NodeMetrics(loc=30, centrality=0.9, complexity=5.0),
            position_hint=PositionHint(cluster_id=2, depth=3),
            ai_summary="Entry point for the CLI.",
        )
        assert node.type == NodeType.FUNCTION
        assert node.metrics.centrality == 0.9

    def test_invalid_type_rejects(self) -> None:
        with pytest.raises(ValidationError):
            GraphNode(id="x", label="x", type="galaxy", path="x")


class TestGraphEdge:
    """GraphEdge validation tests."""

    def test_valid_edge(self) -> None:
        edge = GraphEdge(
            id="e-1", source="a", target="b", relation=EdgeRelation.IMPORTS
        )
        assert edge.weight == 1.0

    def test_invalid_relation_rejects(self) -> None:
        with pytest.raises(ValidationError):
            GraphEdge(id="e-1", source="a", target="b", relation="teleports")


class TestWorkflow:
    """Workflow validation tests."""

    def test_empty_workflow(self) -> None:
        wf = Workflow(id="wf-1", name="Test Flow")
        assert wf.ordered_node_ids == []
        assert wf.edge_ids == []

    def test_populated_workflow(self) -> None:
        wf = Workflow(
            id="wf-1",
            name="Auth Flow",
            description="Authentication lifecycle",
            ordered_node_ids=["a", "b", "c"],
            edge_ids=["e-1", "e-2"],
        )
        assert len(wf.ordered_node_ids) == 3


class TestAstralGraph:
    """AstralGraph top-level model tests."""

    def test_minimal_graph(self) -> None:
        g = AstralGraph(repo_url="https://github.com/test/repo", repo_name="repo")
        assert g.branch == "main"
        assert g.nodes == []
        assert g.edges == []

    def test_roundtrip_serialization(self) -> None:
        """Serialize to JSON and back without data loss."""
        g = AstralGraph(
            repo_url="https://github.com/test/repo",
            repo_name="repo",
            nodes=[
                GraphNode(id="n-1", label="main.py", type=NodeType.FILE, path="main.py")
            ],
            edges=[
                GraphEdge(id="e-1", source="n-1", target="n-1", relation=EdgeRelation.CONTAINS)
            ],
            workflows=[
                Workflow(id="wf-1", name="Boot", ordered_node_ids=["n-1"], edge_ids=["e-1"])
            ],
        )
        json_str = g.model_dump_json()
        restored = AstralGraph.model_validate_json(json_str)
        assert restored.repo_name == "repo"
        assert len(restored.nodes) == 1
        assert restored.nodes[0].id == "n-1"
        assert len(restored.workflows) == 1
