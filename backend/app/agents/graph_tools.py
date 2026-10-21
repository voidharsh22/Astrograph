"""
LangChain Graph Tools for Astral Cartographer (Phase 3).

Exposes tools decorated with `@tool` to allow LangGraph agents (such as the Q&A Agent)
to query the NetworkX dependency graph, search nodes, trace execution dependencies,
and retrieve galaxy cluster summaries without reading the entire repository.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, tool

from app.services.graph_store import GraphStore, get_active_graph_store


# ---------------------------------------------------------------------------
# Global Tools (bind to the active GraphStore)
# ---------------------------------------------------------------------------

@tool
def search_nodes_by_keyword(query: str) -> list[dict[str, Any]]:
    """
    Search the codebase graph for nodes matching a keyword, symbol name, or path.

    Use this tool when you need to find relevant classes, functions, or files
    related to a concept (e.g. 'auth', 'database', 'parser', 'cartographer', 'handler').

    Args:
        query: The search term or symbol name (e.g., 'jwt', 'login', 'Cartographer').

    Returns:
        A list of matching node dictionaries containing id, label, type, path,
        centrality score, cluster_id, and any existing AI summaries.
    """
    store = get_active_graph_store()
    return store.search_nodes_by_keyword(query, limit=10)


@tool
def get_node_dependencies(node_id: str, depth: int = 1) -> dict[str, Any]:
    """
    Explore the topological dependencies (inbound and outbound) for a specific node in the codebase.

    Use this tool to see what functions/files call this node (inbound) and what
    dependencies/imports this node relies on (outbound).

    Args:
        node_id: The exact ID of the node to inspect (e.g. 'file::backend/app/main.py' or 'func::app/services/cartographer.py::build_graph').
        depth: Traversal depth hops (default 1).

    Returns:
        A dictionary containing the node metadata, inbound callers/importers,
        and outbound dependencies/imports.
    """
    store = get_active_graph_store()
    return store.get_node_dependencies(node_id, depth=depth)


@tool
def get_cluster_summary(cluster_id: int) -> str:
    """
    Retrieve a structural summary of a Louvain community cluster (a 'Galaxy' module).

    Use this tool to understand the architectural purpose of a cluster of related files
    and discover its most central/authoritative nodes.

    Args:
        cluster_id: The integer ID of the cluster to inspect (e.g. 0, 1, 2).

    Returns:
        A formatted string describing the cluster, its primary directories,
        languages, and the top nodes ranked by PageRank centrality.
    """
    store = get_active_graph_store()
    return store.get_cluster_summary(cluster_id)


# ---------------------------------------------------------------------------
# Tool Factory (for graph-scoped toolsets)
# ---------------------------------------------------------------------------

def create_graph_tools(store: GraphStore | None = None) -> list[BaseTool]:
    """
    Create a set of LangChain tools optionally bound to a specific GraphStore instance.

    If store is None, the global active graph store is used.
    """
    target_store = store or get_active_graph_store()

    @tool
    def search_nodes(query: str) -> list[dict[str, Any]]:
        """Search the codebase graph for nodes matching a keyword, symbol name, or path."""
        return target_store.search_nodes_by_keyword(query, limit=10)

    @tool
    def get_dependencies(node_id: str, depth: int = 1) -> dict[str, Any]:
        """Explore inbound and outbound topological dependencies for a specific node."""
        return target_store.get_node_dependencies(node_id, depth=depth)

    @tool
    def get_cluster(cluster_id: int) -> str:
        """Retrieve a structural summary of a Louvain community cluster."""
        return target_store.get_cluster_summary(cluster_id)

    # Set canonical names
    search_nodes.name = "search_nodes_by_keyword"
    get_dependencies.name = "get_node_dependencies"
    get_cluster.name = "get_cluster_summary"

    return [search_nodes, get_dependencies, get_cluster]


DEFAULT_GRAPH_TOOLS = [
    search_nodes_by_keyword,
    get_node_dependencies,
    get_cluster_summary,
]
