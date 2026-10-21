"""
In-memory Graph Store for Astral Cartographer.

Manages the dual representation of the codebase knowledge base:
1. `AstralGraph` (Pydantic schema serialized for API & 3D frontend)
2. `networkx.DiGraph` (Graph topology for PageRank, community detection, traversal)

Powers fast keyword lookups, dependency exploration, and cluster aggregation
for LangChain tools and LangGraph agents.
"""
from __future__ import annotations
from app.agents import workflow_agent

import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx

from app.schemas.graph_schema import AstralGraph, GraphNode, Workflow

logger = logging.getLogger(__name__)

_DEMO_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "demo_galaxy.json"


class GraphStore:
    """In-memory index and topology wrapper around an AstralGraph and NetworkX DiGraph."""

    def __init__(self, graph: AstralGraph) -> None:
        self.graph = graph
        self.nodes_by_id: dict[str, GraphNode] = {node.id: node for node in graph.nodes}
        self.clusters: dict[int, list[GraphNode]] = {}
        for node in graph.nodes:
            cid = node.position_hint.cluster_id
            self.clusters.setdefault(cid, []).append(node)

        self.cluster_summaries: dict[int, str] = dict(
            getattr(graph.metadata, "cluster_summaries", {})
        )

        # Build NetworkX DiGraph topology
        self.nx_graph: nx.DiGraph = nx.DiGraph()
        for node in graph.nodes:
            self.nx_graph.add_node(
                node.id,
                label=node.label,
                type=node.type.value,
                language=node.language,
                path=node.path,
                loc=node.metrics.loc,
                centrality=node.metrics.centrality,
                complexity=node.metrics.complexity,
                cluster_id=node.position_hint.cluster_id,
                depth=node.position_hint.depth,
                ai_summary=node.ai_summary or "",
            )

        for edge in graph.edges:
            self.nx_graph.add_edge(
                edge.source,
                edge.target,
                id=edge.id,
                relation=edge.relation.value,
                weight=edge.weight,
            )

    # -----------------------------------------------------------------------
    # Tool Methods
    # -----------------------------------------------------------------------

    def search_nodes_by_keyword(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Search graph nodes by keyword matching against label, path, ID, and AI summary.

        Results are scored by exact match, substring matches, and centrality.
        """
        if not query or not query.strip():
            return []

        q = query.strip().lower()
        scored_nodes: list[tuple[float, GraphNode]] = []

        for node in self.graph.nodes:
            score = 0.0
            label_lower = node.label.lower()
            path_lower = node.path.lower()
            id_lower = node.id.lower()
            summary_lower = (node.ai_summary or "").lower()

            # Exact match on label or stem
            if label_lower == q or label_lower.rstrip("()") == q:
                score += 50.0
            elif q in label_lower:
                score += 25.0

            # Path matches
            if path_lower.endswith(q) or f"/{q}" in path_lower:
                score += 20.0
            elif q in path_lower:
                score += 10.0

            # ID matches
            if q in id_lower:
                score += 10.0

            # Summary content match
            if summary_lower and q in summary_lower:
                score += 8.0

            # Type match (e.g. query "class" or "function")
            if node.type.value == q:
                score += 2.0

            if score > 0.0:
                # Centrality boosts relevance for important core modules
                score += node.metrics.centrality * 5.0
                scored_nodes.append((score, node))

        # Sort descending by score
        scored_nodes.sort(key=lambda item: item[0], reverse=True)

        results: list[dict[str, Any]] = []
        for _, n in scored_nodes[:limit]:
            results.append(
                {
                    "id": n.id,
                    "label": n.label,
                    "type": n.type.value,
                    "path": n.path,
                    "centrality": n.metrics.centrality,
                    "cluster_id": n.position_hint.cluster_id,
                    "ai_summary": n.ai_summary or "",
                }
            )

        return results

    def get_node_dependencies(self, node_id: str, depth: int = 1) -> dict[str, Any]:
        """
        Retrieve inbound (callers/importers) and outbound (dependencies/callees) edges
        for a given node in the NetworkX graph.
        """
        if node_id not in self.nodes_by_id:
            # Try fuzzy lookup by matching suffix or label
            clean_id = node_id.strip()
            matches = [n for n in self.graph.nodes if n.label.lower() == clean_id.lower()]
            if matches:
                node_id = matches[0].id
            else:
                return {
                    "error": f"Node '{node_id}' not found in graph topology.",
                    "node_id": node_id,
                    "inbound_dependencies": [],
                    "outbound_dependencies": [],
                }

        node = self.nodes_by_id[node_id]
        inbound: list[dict[str, Any]] = []
        outbound: list[dict[str, Any]] = []

        # Outbound edges: node -> target
        if self.nx_graph.has_node(node_id):
            for _, target, edge_data in self.nx_graph.out_edges(node_id, data=True):
                target_node = self.nodes_by_id.get(target)
                outbound.append(
                    {
                        "target_id": target,
                        "label": target_node.label if target_node else target,
                        "type": target_node.type.value if target_node else "unknown",
                        "relation": edge_data.get("relation", "unknown"),
                        "ai_summary": (target_node.ai_summary or "") if target_node else "",
                    }
                )

            # Inbound edges: source -> node
            for source, _, edge_data in self.nx_graph.in_edges(node_id, data=True):
                source_node = self.nodes_by_id.get(source)
                inbound.append(
                    {
                        "source_id": source,
                        "label": source_node.label if source_node else source,
                        "type": source_node.type.value if source_node else "unknown",
                        "relation": edge_data.get("relation", "unknown"),
                        "ai_summary": (source_node.ai_summary or "") if source_node else "",
                    }
                )

        return {
            "node_id": node.id,
            "label": node.label,
            "type": node.type.value,
            "path": node.path,
            "centrality": node.metrics.centrality,
            "cluster_id": node.position_hint.cluster_id,
            "ai_summary": node.ai_summary or "",
            "inbound_dependencies": inbound,
            "outbound_dependencies": outbound,
        }

    def get_cluster_summary(self, cluster_id: int) -> str:
        """
        Aggregate and describe nodes belonging to a Louvain community cluster.

        Extracts the top 3-5 most central nodes by PageRank and formats a cluster profile.
        """
        cluster_nodes = self.clusters.get(cluster_id, [])
        if not cluster_nodes:
            return f"Cluster {cluster_id} contains no nodes or does not exist."

        # Rank by centrality descending
        sorted_nodes = sorted(cluster_nodes, key=lambda n: n.metrics.centrality, reverse=True)
        top_nodes = sorted_nodes[:5]

        # Gather directory paths and languages
        paths = {n.path.split("/")[0] for n in cluster_nodes if "/" in n.path}
        languages = {n.language for n in cluster_nodes if n.language}

        node_details = []
        for n in top_nodes:
            summary = n.ai_summary or "No summary available"
            node_details.append(
                f"- **{n.label}** (`{n.type.value}` at `{n.path}`, centrality: {n.metrics.centrality}): {summary}"
            )

        galaxy_summary_line = ""
        if cluster_id in self.cluster_summaries:
            galaxy_summary_line = f"**Galaxy Summary**: {self.cluster_summaries[cluster_id]}\n\n"

        profile = (
            f"### Galaxy Cluster {cluster_id} Profile\n"
            f"{galaxy_summary_line}"
            f"- **Total Nodes**: {len(cluster_nodes)}\n"
            f"- **Languages**: {', '.join(sorted(languages)) if languages else 'Not specified'}\n"
            f"- **Top Modules/Directories**: {', '.join(sorted(paths)) if paths else 'Root'}\n\n"
            f"**Key Central Nodes (Top PageRank):**\n"
            + "\n".join(node_details)
        )
        return profile

    def set_cluster_summaries(self, summaries: dict[int, str]) -> None:
        """Store synthesized Galaxy summaries and mutate the underlying AstralGraph metadata."""
        self.cluster_summaries.update(summaries)
        self.graph.metadata.cluster_summaries.update(summaries)

    def set_workflows(self, workflows: list[Workflow]) -> None:
        """Store traced execution workflows on the AstralGraph."""
        self.graph.workflows = workflows



# ---------------------------------------------------------------------------
# Singleton / Global Active Store Management
# ---------------------------------------------------------------------------

_active_store: GraphStore | None = None


def get_active_graph_store() -> GraphStore:
    """Retrieve the currently active graph store. If none set, initializes with demo graph."""
    global _active_store  # noqa: PLW0603
    if _active_store is None:
        try:
            if _DEMO_DATA_PATH.exists():
                raw = json.loads(_DEMO_DATA_PATH.read_text(encoding="utf-8"))
                demo_graph = AstralGraph.model_validate(raw)
                _active_store = GraphStore(demo_graph)
            else:
                _active_store = GraphStore(
                    AstralGraph(repo_url="demo", repo_name="demo-empty", branch="main")
                )
        except Exception as exc:
            logger.warning("Failed to initialize demo GraphStore: %s", exc)
            _active_store = GraphStore(
                AstralGraph(repo_url="demo", repo_name="demo-empty", branch="main")
            )
    return _active_store


def set_active_graph_store(store: GraphStore) -> None:
    """Set the currently active graph store."""
    global _active_store  # noqa: PLW0603
    _active_store = store
