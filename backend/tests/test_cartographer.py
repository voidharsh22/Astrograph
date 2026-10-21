"""Tests for the cartographer (graph engine) service."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from app.schemas.graph_schema import AstralGraph, NodeType, EdgeRelation
from app.services.cartographer import (
    _build_networkx_graph,
    _compute_communities,
    _compute_pagerank,
    _serialize_graph,
    _parse_all_files,
)
from app.services.ingestor import FileInfo, RepoData


def _make_repo_data(files: list[FileInfo]) -> RepoData:
    """Helper to create a minimal RepoData for testing."""
    return RepoData(
        clone_path=Path("."),
        repo_name="test-repo",
        repo_url="https://github.com/test/repo",
        branch="main",
        commit_sha="abc123",
        files=files,
    )


class TestNetworkXGraphConstruction:
    """Tests for the graph building logic."""

    def test_creates_directory_nodes(self) -> None:
        files = [
            FileInfo(path="src/main.py", language="python", loc=10, size_bytes=200),
            FileInfo(path="src/utils/helpers.py", language="python", loc=5, size_bytes=100),
        ]
        G = _build_networkx_graph(files, {})

        dir_nodes = [n for n, d in G.nodes(data=True) if d["type"] == "directory"]
        assert "dir::src" in dir_nodes
        assert "dir::src/utils" in dir_nodes

    def test_creates_file_nodes(self) -> None:
        files = [
            FileInfo(path="src/main.py", language="python", loc=10, size_bytes=200),
        ]
        G = _build_networkx_graph(files, {})

        assert "file::src/main.py" in G.nodes()
        assert G.nodes["file::src/main.py"]["type"] == "file"
        assert G.nodes["file::src/main.py"]["language"] == "python"

    def test_creates_containment_edges(self) -> None:
        files = [
            FileInfo(path="src/main.py", language="python", loc=10, size_bytes=200),
        ]
        G = _build_networkx_graph(files, {})

        assert G.has_edge("dir::src", "file::src/main.py")
        assert G["dir::src"]["file::src/main.py"]["relation"] == "contains"

    def test_creates_symbol_nodes_from_parse_results(self) -> None:
        from app.services.parsers.base import ParsedSymbol, ParseResult

        files = [
            FileInfo(path="app.py", language="python", loc=20, size_bytes=400),
        ]
        parse_results = {
            "app.py": ParseResult(
                file_path="app.py",
                language="python",
                symbols=[
                    ParsedSymbol(name="main", kind="function", line_start=1, line_end=5),
                    ParsedSymbol(name="App", kind="class", line_start=7, line_end=20, bases=[]),
                ],
                imports=[],
                loc=20,
            )
        }
        G = _build_networkx_graph(files, parse_results)

        assert "func::app.py::main" in G.nodes()
        assert "class::app.py::App" in G.nodes()
        assert G.has_edge("file::app.py", "func::app.py::main")
        assert G.has_edge("file::app.py", "class::app.py::App")

    def test_creates_import_edges_from_parse_results(self) -> None:
        from app.services.parsers.base import ParsedImport, ParseResult

        files = [
            FileInfo(path="main.py", language="python", loc=10, size_bytes=200),
            FileInfo(path="utils.py", language="python", loc=5, size_bytes=100),
        ]
        parse_results = {
            "main.py": ParseResult(
                file_path="main.py",
                language="python",
                symbols=[],
                imports=[
                    ParsedImport(
                        raw_statement="from utils import helper",
                        resolved_path="utils.py",
                        imported_names=["helper"],
                    )
                ],
                loc=10,
            )
        }
        G = _build_networkx_graph(files, parse_results)

        assert G.has_edge("file::main.py", "file::utils.py")
        assert G["file::main.py"]["file::utils.py"]["relation"] == "imports"


class TestMetrics:
    """Tests for PageRank and community detection."""

    def test_pagerank_on_simple_graph(self) -> None:
        G = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("b", "c")
        G.add_edge("c", "a")

        pr = _compute_pagerank(G)
        assert len(pr) == 3
        assert all(v > 0 for v in pr.values())

    def test_pagerank_on_empty_graph(self) -> None:
        G = nx.DiGraph()
        pr = _compute_pagerank(G)
        assert pr == {}

    def test_community_detection(self) -> None:
        G = nx.DiGraph()
        # Two clusters
        G.add_edge("a1", "a2")
        G.add_edge("a2", "a3")
        G.add_edge("b1", "b2")
        G.add_edge("b2", "b3")

        clusters = _compute_communities(G)
        assert len(clusters) == 6
        # Nodes in the same cluster should have the same cluster_id
        assert clusters["a1"] == clusters["a2"] == clusters["a3"]
        assert clusters["b1"] == clusters["b2"] == clusters["b3"]

    def test_community_empty_graph(self) -> None:
        G = nx.DiGraph()
        clusters = _compute_communities(G)
        assert clusters == {}


class TestSerialization:
    """Tests for graph serialization into AstralGraph."""

    def test_serializes_to_valid_astral_graph(self) -> None:
        files = [
            FileInfo(path="src/main.py", language="python", loc=10, size_bytes=200),
            FileInfo(path="src/utils.py", language="python", loc=5, size_bytes=100),
        ]
        repo_data = _make_repo_data(files)
        G = _build_networkx_graph(files, {})
        pr = _compute_pagerank(G)
        dc = nx.degree_centrality(G)
        clusters = _compute_communities(G)

        graph = _serialize_graph(
            repo_data=repo_data,
            G=G,
            parse_results={},
            pagerank=pr,
            degree_centrality=dc,
            clusters=clusters,
            elapsed_ms=42.0,
        )

        assert isinstance(graph, AstralGraph)
        assert graph.repo_name == "test-repo"
        assert len(graph.nodes) > 0
        assert len(graph.edges) > 0  # dir::src --contains--> file nodes
        assert graph.metadata.total_files == 2
        assert graph.metadata.analysis_duration_ms == 42.0

    def test_centrality_is_normalized(self) -> None:
        files = [
            FileInfo(path="a.py", language="python", loc=10, size_bytes=200),
            FileInfo(path="b.py", language="python", loc=5, size_bytes=100),
        ]
        repo_data = _make_repo_data(files)
        G = _build_networkx_graph(files, {})
        pr = _compute_pagerank(G)
        dc = nx.degree_centrality(G)
        clusters = _compute_communities(G)

        graph = _serialize_graph(
            repo_data=repo_data,
            G=G,
            parse_results={},
            pagerank=pr,
            degree_centrality=dc,
            clusters=clusters,
            elapsed_ms=10.0,
        )

        for node in graph.nodes:
            assert 0.0 <= node.metrics.centrality <= 1.0

    def test_node_types_are_valid_enums(self) -> None:
        files = [
            FileInfo(path="src/app.py", language="python", loc=10, size_bytes=200),
        ]
        repo_data = _make_repo_data(files)
        G = _build_networkx_graph(files, {})
        pr = _compute_pagerank(G)
        dc = nx.degree_centrality(G)
        clusters = _compute_communities(G)

        graph = _serialize_graph(
            repo_data=repo_data,
            G=G,
            parse_results={},
            pagerank=pr,
            degree_centrality=dc,
            clusters=clusters,
            elapsed_ms=5.0,
        )

        for node in graph.nodes:
            assert node.type in NodeType

    def test_edge_relations_are_valid_enums(self) -> None:
        files = [
            FileInfo(path="src/app.py", language="python", loc=10, size_bytes=200),
        ]
        repo_data = _make_repo_data(files)
        G = _build_networkx_graph(files, {})
        pr = _compute_pagerank(G)
        dc = nx.degree_centrality(G)
        clusters = _compute_communities(G)

        graph = _serialize_graph(
            repo_data=repo_data,
            G=G,
            parse_results={},
            pagerank=pr,
            degree_centrality=dc,
            clusters=clusters,
            elapsed_ms=5.0,
        )

        for edge in graph.edges:
            assert edge.relation in EdgeRelation
