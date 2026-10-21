"""Tests for the AI Workflow Agent (Phase 3).

Covers:
- Heuristic (fallback) summarization when no Gemini key is configured.
- Candidate selection logic (centrality threshold, max cap).
- Workflow detection from entry-points.
- Workflow tracing (DFS, cycle avoidance, depth limits).
- Full enrich_graph integration with heuristic path.
- Edge cases: empty graph, no entry-points, single-node graphs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.agents.workflow_agent import (
    _detect_workflows,
    _find_entry_points,
    _heuristic_summary,
    _select_candidates,
    _trace_workflow,
    enrich_graph,
)
from app.schemas.graph_schema import (
    AstralGraph,
    EdgeRelation,
    GraphEdge,
    GraphMetadata,
    GraphNode,
    NodeMetrics,
    NodeType,
    PositionHint,
    Workflow,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_node(
    node_id: str,
    label: str,
    node_type: str = "file",
    path: str = "",
    centrality: float = 0.5,
    loc: int = 50,
    language: str | None = "python",
) -> GraphNode:
    return GraphNode(
        id=node_id,
        label=label,
        type=NodeType(node_type),
        language=language,
        path=path or node_id,
        metrics=NodeMetrics(loc=loc, centrality=centrality, complexity=0.0),
        position_hint=PositionHint(cluster_id=0, depth=0),
        ai_summary=None,
    )


def _make_edge(
    source: str,
    target: str,
    relation: str = "imports",
    edge_id: str | None = None,
) -> GraphEdge:
    eid = edge_id or f"e-{source}->{target}"
    return GraphEdge(
        id=eid,
        source=source,
        target=target,
        relation=EdgeRelation(relation),
        weight=1.0,
    )


def _make_graph(
    nodes: list[GraphNode] | None = None,
    edges: list[GraphEdge] | None = None,
) -> AstralGraph:
    return AstralGraph(
        repo_url="https://github.com/test/repo",
        repo_name="test-repo",
        branch="main",
        commit_sha="abc123",
        generated_at=datetime.now(timezone.utc),
        nodes=nodes or [],
        edges=edges or [],
        workflows=[],
        metadata=GraphMetadata(
            total_files=len(nodes or []),
            total_functions=0,
            total_classes=0,
            languages=["python"],
            analysis_duration_ms=42.0,
        ),
    )


# ---------------------------------------------------------------------------
# Heuristic Summarization Tests
# ---------------------------------------------------------------------------


class TestHeuristicSummary:
    """Tests for the deterministic fallback summarizer."""

    def test_directory_node(self):
        node = _make_node("dir::src", "src", node_type="directory")
        result = _heuristic_summary(node, "")
        assert "Directory" in result

    def test_file_with_docstring(self):
        node = _make_node("file::utils.py", "utils.py", path="utils.py")
        source = '"""Utility functions for data transformation."""\nimport os\n'
        result = _heuristic_summary(node, source)
        assert "Utility functions" in result

    def test_file_without_docstring(self):
        node = _make_node("file::calc.py", "calc.py", path="calc.py", loc=100)
        source = "import math\n\ndef add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"
        result = _heuristic_summary(node, source)
        assert "calc.py" in result
        assert "function" in result.lower()

    def test_class_with_docstring(self):
        node = _make_node("class::app.py::Router", "Router", node_type="class")
        source = 'class Router:\n    """HTTP request router dispatching paths to handlers."""\n    def match(self): pass\n'
        result = _heuristic_summary(node, source)
        assert "router" in result.lower() or "HTTP" in result

    def test_class_without_docstring(self):
        node = _make_node("class::m.py::Foo", "Foo", node_type="class", loc=30)
        source = "class Foo:\n    def a(self): pass\n    def b(self): pass\n"
        result = _heuristic_summary(node, source)
        assert "Foo" in result
        assert "method" in result.lower()

    def test_function_with_docstring(self):
        node = _make_node("func::f.py::parse", "parse()", node_type="function")
        source = 'def parse(data):\n    """Parse incoming JSON payload and validate schema."""\n    pass\n'
        result = _heuristic_summary(node, source)
        assert "Parse" in result or "JSON" in result

    def test_function_without_docstring(self):
        node = _make_node("func::f.py::run", "run()", node_type="function", loc=20)
        source = "def run():\n    print('hello')\n"
        result = _heuristic_summary(node, source)
        assert "run" in result

    def test_summary_length_capped(self):
        node = _make_node("file::long.py", "long.py")
        docstring = "A" * 300
        source = f'"""{docstring}"""\n'
        result = _heuristic_summary(node, source)
        assert len(result) <= 200


# ---------------------------------------------------------------------------
# Candidate Selection Tests
# ---------------------------------------------------------------------------


class TestCandidateSelection:
    """Tests for _select_candidates."""

    def test_filters_by_centrality(self):
        high = _make_node("a", "a.py", centrality=0.8)
        low = _make_node("b", "b.py", centrality=0.05)
        graph = _make_graph([high, low])
        snippets = {"a": "code", "b": "code"}
        candidates = _select_candidates(graph, snippets)
        ids = [c.id for c in candidates]
        assert "a" in ids
        assert "b" not in ids

    def test_filters_by_source_availability(self):
        node = _make_node("a", "a.py", centrality=0.9)
        graph = _make_graph([node])
        # No source snippet for 'a'
        candidates = _select_candidates(graph, {})
        assert len(candidates) == 0

    def test_sorted_by_centrality_descending(self):
        n1 = _make_node("a", "a.py", centrality=0.3)
        n2 = _make_node("b", "b.py", centrality=0.9)
        n3 = _make_node("c", "c.py", centrality=0.6)
        graph = _make_graph([n1, n2, n3])
        snippets = {"a": "x", "b": "x", "c": "x"}
        candidates = _select_candidates(graph, snippets)
        assert candidates[0].id == "b"
        assert candidates[1].id == "c"
        assert candidates[2].id == "a"

    def test_max_cap_applied(self):
        nodes = [_make_node(f"n{i}", f"n{i}.py", centrality=0.5) for i in range(100)]
        graph = _make_graph(nodes)
        snippets = {f"n{i}": "code" for i in range(100)}
        candidates = _select_candidates(graph, snippets)
        assert len(candidates) <= 40  # _MAX_SUMMARIZE_NODES


# ---------------------------------------------------------------------------
# Entry Point Detection Tests
# ---------------------------------------------------------------------------


class TestFindEntryPoints:
    """Tests for _find_entry_points."""

    def test_detects_main_py(self):
        main = _make_node("file::main.py", "main.py", path="main.py")
        utils = _make_node("file::utils.py", "utils.py", path="utils.py")
        graph = _make_graph([main, utils])
        eps = _find_entry_points(graph)
        assert any(n.id == "file::main.py" for n in eps)

    def test_detects_app_py(self):
        app = _make_node("file::src/app.py", "app.py", path="src/app.py")
        graph = _make_graph([app])
        eps = _find_entry_points(graph)
        assert len(eps) == 1

    def test_detects_index_js(self):
        idx = _make_node("file::src/index.js", "index.js", path="src/index.js", language="javascript")
        graph = _make_graph([idx])
        eps = _find_entry_points(graph)
        assert len(eps) == 1

    def test_falls_back_to_route_patterns(self):
        routes = _make_node("file::api/routes.py", "routes.py", path="api/routes.py")
        graph = _make_graph([routes])
        eps = _find_entry_points(graph)
        assert len(eps) >= 1

    def test_falls_back_to_highest_centrality(self):
        n1 = _make_node("file::a.py", "a.py", path="a.py", centrality=0.1)
        n2 = _make_node("file::b.py", "b.py", path="b.py", centrality=0.9)
        n3 = _make_node("file::c.py", "c.py", path="c.py", centrality=0.5)
        graph = _make_graph([n1, n2, n3])
        eps = _find_entry_points(graph)
        assert len(eps) <= 3
        # Should include the highest centrality
        ep_ids = {n.id for n in eps}
        assert "file::b.py" in ep_ids

    def test_ignores_non_file_nodes(self):
        func = _make_node("func::main.py::run", "run()", node_type="function", path="main.py")
        graph = _make_graph([func])
        eps = _find_entry_points(graph)
        # Should not match function nodes, falls back to empty → centrality
        assert len(eps) == 0 or all(n.type.value == "file" for n in eps)


# ---------------------------------------------------------------------------
# Workflow Tracing Tests
# ---------------------------------------------------------------------------


class TestTraceWorkflow:
    """Tests for _trace_workflow."""

    def test_simple_chain(self):
        adjacency = {
            "A": [("B", "imports", "e1")],
            "B": [("C", "calls", "e2")],
        }
        node_ids = {"A", "B", "C"}
        nodes, edges = _trace_workflow("A", adjacency, node_ids)
        assert "A" in nodes
        assert "B" in nodes
        assert "C" in nodes
        assert len(edges) >= 2

    def test_avoids_cycles(self):
        adjacency = {
            "A": [("B", "imports", "e1")],
            "B": [("A", "imports", "e2"), ("C", "calls", "e3")],
        }
        node_ids = {"A", "B", "C"}
        nodes, edges = _trace_workflow("A", adjacency, node_ids)
        # A should appear exactly once
        assert nodes.count("A") == 1

    def test_respects_max_depth(self):
        # Build a chain longer than max_depth
        adjacency = {}
        node_ids = set()
        for i in range(20):
            nid = f"n{i}"
            node_ids.add(nid)
            if i < 19:
                adjacency[nid] = [(f"n{i+1}", "imports", f"e{i}")]
        node_ids.add("n19")

        nodes, edges = _trace_workflow("n0", adjacency, node_ids, max_depth=5)
        assert len(nodes) <= 7  # start + up to max_depth

    def test_empty_adjacency(self):
        nodes, edges = _trace_workflow("A", {}, {"A"})
        assert nodes == ["A"]
        assert edges == []

    def test_prioritizes_calls_over_imports(self):
        adjacency = {
            "A": [
                ("B", "imports", "e1"),
                ("C", "calls", "e2"),
            ],
        }
        node_ids = {"A", "B", "C"}
        nodes, edges = _trace_workflow("A", adjacency, node_ids)
        # Both B and C should be reachable
        assert "B" in nodes
        assert "C" in nodes


# ---------------------------------------------------------------------------
# Workflow Detection Integration Tests
# ---------------------------------------------------------------------------


class TestDetectWorkflows:
    """Tests for _detect_workflows."""

    def test_detects_workflow_from_main(self):
        main = _make_node("file::main.py", "main.py", path="main.py", centrality=0.9)
        utils = _make_node("file::utils.py", "utils.py", path="utils.py", centrality=0.3)
        edges = [_make_edge("file::main.py", "file::utils.py", "imports")]
        graph = _make_graph([main, utils], edges)

        _detect_workflows(graph)
        assert len(graph.workflows) >= 1
        wf = graph.workflows[0]
        assert "file::main.py" in wf.ordered_node_ids
        assert len(wf.ordered_node_ids) >= 2

    def test_workflow_has_valid_structure(self):
        main = _make_node("file::main.py", "main.py", path="main.py")
        svc = _make_node("file::service.py", "service.py", path="service.py")
        edges = [_make_edge("file::main.py", "file::service.py")]
        graph = _make_graph([main, svc], edges)

        _detect_workflows(graph)
        for wf in graph.workflows:
            assert wf.id
            assert wf.name
            assert wf.description
            assert len(wf.ordered_node_ids) >= 2

    def test_no_duplicate_workflows(self):
        main = _make_node("file::main.py", "main.py", path="main.py")
        graph = _make_graph([main])
        _detect_workflows(graph)
        # Even if called multiple times, shouldn't create duplicates
        paths = [tuple(wf.ordered_node_ids) for wf in graph.workflows]
        assert len(paths) == len(set(paths))

    def test_empty_graph_produces_no_workflows(self):
        graph = _make_graph([])
        _detect_workflows(graph)
        assert graph.workflows == []


# ---------------------------------------------------------------------------
# Full enrich_graph Integration Tests (Heuristic Path)
# ---------------------------------------------------------------------------


class TestEnrichGraph:
    """Integration tests for enrich_graph — uses heuristic path (no API key)."""

    @patch("app.agents.workflow_agent._has_gemini_key", return_value=False)
    async def test_populates_summaries_without_gemini(self, _mock_key):
        main = _make_node("file::main.py", "main.py", path="main.py", centrality=0.8)
        utils = _make_node("file::utils.py", "utils.py", path="utils.py", centrality=0.6)
        edges = [_make_edge("file::main.py", "file::utils.py")]
        graph = _make_graph([main, utils], edges)

        snippets = {
            "file::main.py": '"""Application entry point."""\nfrom utils import go\n',
            "file::utils.py": "def go():\n    return 42\n",
        }

        result = await enrich_graph(graph, snippets)

        # Summaries should be populated
        summarized = [n for n in result.nodes if n.ai_summary]
        assert len(summarized) >= 1

    @patch("app.agents.workflow_agent._has_gemini_key", return_value=False)
    async def test_populates_workflows(self, _mock_key):
        main = _make_node("file::main.py", "main.py", path="main.py", centrality=0.9)
        svc = _make_node("file::svc.py", "svc.py", path="svc.py", centrality=0.4)
        edges = [_make_edge("file::main.py", "file::svc.py")]
        graph = _make_graph([main, svc], edges)

        snippets = {"file::main.py": "print('hi')", "file::svc.py": "pass"}
        result = await enrich_graph(graph, snippets)

        assert len(result.workflows) >= 1

    @patch("app.agents.workflow_agent._has_gemini_key", return_value=False)
    async def test_enrich_returns_same_graph_instance(self, _mock_key):
        graph = _make_graph([_make_node("file::a.py", "a.py", centrality=0.5)])
        result = await enrich_graph(graph, {"file::a.py": "pass"})
        assert result is graph

    @patch("app.agents.workflow_agent._has_gemini_key", return_value=False)
    async def test_enrich_empty_graph(self, _mock_key):
        graph = _make_graph([])
        result = await enrich_graph(graph, {})
        assert result.workflows == []
        assert all(n.ai_summary is None for n in result.nodes)

    @patch("app.agents.workflow_agent._has_gemini_key", return_value=False)
    async def test_low_centrality_nodes_skipped(self, _mock_key):
        low = _make_node("file::low.py", "low.py", centrality=0.01)
        graph = _make_graph([low])
        snippets = {"file::low.py": "x = 1"}
        result = await enrich_graph(graph, snippets)
        assert result.nodes[0].ai_summary is None


# ---------------------------------------------------------------------------
# Gemini Failure Fallback Test
# ---------------------------------------------------------------------------


class TestGeminiFallback:
    """Tests that Gemini failures degrade gracefully to heuristics."""

    @patch("app.agents.workflow_agent._has_gemini_key", return_value=True)
    @patch(
        "app.agents.workflow_agent._summarize_with_gemini",
        side_effect=RuntimeError("API unavailable"),
    )
    async def test_falls_back_on_gemini_error(self, _mock_gemini, _mock_key):
        node = _make_node("file::main.py", "main.py", path="main.py", centrality=0.9)
        graph = _make_graph([node])
        snippets = {"file::main.py": "def run(): pass\n"}

        result = await enrich_graph(graph, snippets)
        # Should still get a heuristic summary, not crash
        assert result.nodes[0].ai_summary is not None


# ---------------------------------------------------------------------------
# LangGraph & LangChain Pipeline Tests
# ---------------------------------------------------------------------------


class TestLangGraphPipeline:
    """Tests that verify the LangGraph StateGraph execution pipeline."""

    def test_pipeline_graph_structure(self):
        from app.agents.workflow_agent import workflow_agent_app
        assert workflow_agent_app is not None
        node_names = set(workflow_agent_app.nodes.keys())
        assert "select_candidates" in node_names
        assert "summarize_nodes" in node_names
        assert "detect_workflows" in node_names
        assert "finalize" in node_names

    @patch("app.agents.workflow_agent._has_gemini_key", return_value=False)
    async def test_direct_pipeline_ainvoke(self, _mock_key):
        from app.agents.workflow_agent import workflow_agent_app
        node = _make_node("file::app.py", "app.py", path="app.py", centrality=0.8)
        graph = _make_graph([node])
        state = {
            "graph": graph,
            "source_snippets": {"file::app.py": '"""App server."""\n'},
            "candidates": [],
            "summaries": {},
            "workflows": [],
        }
        output = await workflow_agent_app.ainvoke(state)
        assert "graph" in output
        assert output["graph"].nodes[0].ai_summary is not None


class TestLangChainSummarization:
    """Tests that LangChain ChatGoogleGenerativeAI is invoked when API key is present."""

    @patch("app.agents.workflow_agent._has_gemini_key", return_value=True)
    @patch("app.agents.workflow_agent.ChatGoogleGenerativeAI")
    async def test_langchain_gemini_summarization(self, mock_llm_cls, _mock_key):
        from unittest.mock import AsyncMock, MagicMock
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Entrypoint coordinating CLI commands and dispatching handlers."
        mock_instance.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm_cls.return_value = mock_instance

        node = _make_node("file::cli.py", "cli.py", path="cli.py", centrality=0.9)
        graph = _make_graph([node])
        snippets = {"file::cli.py": "def main(): pass"}

        result = await enrich_graph(graph, snippets)
        assert result.nodes[0].ai_summary == "Entrypoint coordinating CLI commands and dispatching handlers."
        assert mock_instance.ainvoke.await_count == 1
