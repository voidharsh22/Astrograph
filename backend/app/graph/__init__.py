"""Astral Cartographer graph package."""

from typing import Any


def __getattr__(name: str) -> Any:
    if name in {
        "CodeGraph",
        "EDGE_TYPE_CALLS",
        "EDGE_TYPE_CONTAINS",
        "EDGE_TYPE_DEFINES",
        "EDGE_TYPE_EXTENDS",
        "EDGE_TYPE_IMPLEMENTS",
        "EDGE_TYPE_EXTENDS",
    "EDGE_TYPE_IMPLEMENTS",
    "EDGE_TYPE_IMPORTS",
    "EDGE_TYPE_RENDERS",
        "EDGE_TYPE_RENDERS",
        "GraphEdge",
        "GraphNode",
        "GraphSummary",
        "NODE_TYPE_ASYNC_FUNCTION",
        "NODE_TYPE_CLASS",
        "NODE_TYPE_DIRECTORY",
        "NODE_TYPE_FILE",
        "NODE_TYPE_FUNCTION",
        "NODE_TYPE_METHOD",
        "NODE_TYPE_REPOSITORY",
        "STATUS_AMBIGUOUS",
        "STATUS_EXTERNAL",
        "STATUS_RESOLVED",
        "STATUS_UNRESOLVED",
        "UnresolvedReference",
    }:
        import app.graph.models as models

        return getattr(models, name)

    if name in {"GraphBuilder", "build_graph"}:
        import app.graph.graph_builder as gb

        return getattr(gb, name)

    if name in {
        "find_node_by_id",
        "find_path",
        "get_incoming_neighbors",
        "get_outgoing_neighbors",
        "impact_analysis",
        "traverse_outgoing",
    }:
        import app.graph.graph_queries as gq

        return getattr(gq, name)

    if name in {"SymbolResolver"}:
        import app.graph.symbol_resolver as sr

        return getattr(sr, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CodeGraph",
    "EDGE_TYPE_CALLS",
    "EDGE_TYPE_CONTAINS",
    "EDGE_TYPE_DEFINES",
    "EDGE_TYPE_IMPORTS",
    "GraphBuilder",
    "GraphEdge",
    "GraphNode",
    "GraphSummary",
    "NODE_TYPE_ASYNC_FUNCTION",
    "NODE_TYPE_CLASS",
    "NODE_TYPE_DIRECTORY",
    "NODE_TYPE_FILE",
    "NODE_TYPE_FUNCTION",
    "NODE_TYPE_METHOD",
    "NODE_TYPE_REPOSITORY",
    "STATUS_AMBIGUOUS",
    "STATUS_EXTERNAL",
    "STATUS_RESOLVED",
    "STATUS_UNRESOLVED",
    "SymbolResolver",
    "UnresolvedReference",
    "build_graph",
    "find_node_by_id",
    "find_path",
    "get_incoming_neighbors",
    "get_outgoing_neighbors",
    "impact_analysis",
    "traverse_outgoing",
]
