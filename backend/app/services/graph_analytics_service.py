"""Graph analytics and intelligence service for Astral Cartographer.

Computes PageRank importance scoring, degree centrality metrics, deterministic Louvain
community clustering, and high-level graph statistics while preserving main's source-of-truth
graph representations and node/edge identities.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from app.config import settings
from app.graph.models import (
    EDGE_TYPE_CALLS,
    EDGE_TYPE_CONTAINS,
    EDGE_TYPE_DEFINES,
    EDGE_TYPE_IMPORTS,
    CodeGraph,
)
from app.storage.repository_store import get_repository

logger = logging.getLogger(__name__)

# Edge relationship weights for centrality & importance scoring
EDGE_WEIGHT_MAP: dict[str, float] = {
    EDGE_TYPE_CONTAINS: 1.0,
    EDGE_TYPE_DEFINES: 1.0,
    EDGE_TYPE_IMPORTS: 0.7,
    EDGE_TYPE_CALLS: 0.6,
    "EXTENDS": 0.8,
    "IMPLEMENTS": 0.7,
    "RENDERS": 0.6,
}
DEFAULT_EDGE_WEIGHT: float = 1.0


def build_networkx_graph(graph: CodeGraph | dict[str, Any]) -> nx.DiGraph:
    """Construct a directed NetworkX graph from a CodeGraph or serialized dictionary.

    Preserves all existing node types, labels, IDs, and edges while enforcing endpoint
    integrity and assigning relationship weights.
    """
    G = nx.DiGraph()

    nodes = graph.nodes if isinstance(graph, CodeGraph) else graph.get("nodes", [])
    edges = graph.edges if isinstance(graph, CodeGraph) else graph.get("edges", [])

    for node in nodes:
        if isinstance(node, dict):
            nid = node["id"]
            ntype = node.get("type", "unknown")
            nlabel = node.get("label", nid)
            nname = node.get("name", "")
            nmeta = node.get("metadata", {})
        else:
            nid = node.id
            ntype = node.type
            nlabel = node.label
            nname = node.name
            nmeta = node.metadata

        path_val = nmeta.get("path") or nmeta.get("file_path", "")
        G.add_node(
            nid,
            type=ntype,
            label=nlabel,
            name=nname,
            path=str(path_val),
            language=nmeta.get("language"),
            loc=nmeta.get("loc", 0),
        )

    for edge in edges:
        if isinstance(edge, dict):
            eid = edge.get("id", "")
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            etype = edge.get("type", EDGE_TYPE_CONTAINS)
            emeta = edge.get("metadata", {})
        else:
            eid = edge.id
            src = edge.source
            tgt = edge.target
            etype = edge.type
            emeta = edge.metadata

        # Only add edges where both endpoints exist in the graph
        if G.has_node(src) and G.has_node(tgt):
            weight = EDGE_WEIGHT_MAP.get(etype, DEFAULT_EDGE_WEIGHT)
            if G.has_edge(src, tgt):
                # Accumulate weight for multiple relationships between same nodes
                G[src][tgt]["weight"] = round(G[src][tgt].get("weight", 1.0) + weight * 0.5, 3)
            else:
                G.add_edge(
                    src,
                    tgt,
                    id=eid,
                    type=etype,
                    weight=weight,
                    **emeta,
                )

    return G


def compute_pagerank(
    G: nx.DiGraph,
    alpha: float = 0.85,
    max_iter: int = 200,
) -> tuple[dict[str, float], dict[str, float]]:
    """Compute raw PageRank scores and normalized centrality in [0.0, 1.0].

    Gracefully handles empty graphs, single-node graphs, disconnected components,
    and power-iteration convergence failures.
    """
    if len(G) == 0:
        return {}, {}

    if len(G) == 1:
        only_node = next(iter(G.nodes()))
        return {only_node: 1.0}, {only_node: 1.0}

    try:
        raw_pr = nx.pagerank(G, alpha=alpha, max_iter=max_iter, weight="weight")
    except nx.PowerIterationFailedConvergence:
        logger.warning("PageRank power iteration failed to converge; falling back to degree centrality")
        raw_pr = nx.degree_centrality(G)
    except Exception as exc:
        logger.warning("PageRank calculation encountered error (%s); falling back to degree centrality", exc)
        try:
            deg = nx.degree_centrality(G)
            if not any(deg.values()):
                val = 1.0 / len(G)
                raw_pr = {n: val for n in G.nodes()}
            else:
                raw_pr = deg
        except Exception:
            val = 1.0 / len(G)
            raw_pr = {n: val for n in G.nodes()}

    max_pr = max(raw_pr.values()) if raw_pr else 1.0
    if max_pr <= 0.0:
        max_pr = 1.0

    normalized_pr = {
        n: round(min(score / max_pr, 1.0), 4)
        for n, score in raw_pr.items()
    }
    raw_pr_rounded = {n: round(score, 6) for n, score in raw_pr.items()}
    return raw_pr_rounded, normalized_pr


def compute_degree_metrics(G: nx.DiGraph) -> dict[str, dict[str, Any]]:
    """Compute in-degree, out-degree, and normalized degree-centrality metrics."""
    if len(G) == 0:
        return {}

    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    try:
        deg_cent = nx.degree_centrality(G)
        in_deg_cent = nx.in_degree_centrality(G)
        out_deg_cent = nx.out_degree_centrality(G)
    except Exception as exc:
        logger.warning("Failed calculating degree centrality (%s); defaulting to 0.0", exc)
        deg_cent = {n: 0.0 for n in G.nodes()}
        in_deg_cent = {n: 0.0 for n in G.nodes()}
        out_deg_cent = {n: 0.0 for n in G.nodes()}

    metrics: dict[str, dict[str, Any]] = {}
    for node in G.nodes():
        metrics[node] = {
            "in_degree": in_deg.get(node, 0),
            "out_degree": out_deg.get(node, 0),
            "degree_centrality": round(deg_cent.get(node, 0.0), 4),
            "in_degree_centrality": round(in_deg_cent.get(node, 0.0), 4),
            "out_degree_centrality": round(out_deg_cent.get(node, 0.0), 4),
        }
    return metrics


def compute_communities(G: nx.DiGraph, seed: int = 42) -> dict[str, int]:
    """Execute deterministic Louvain community detection on the undirected projection.

    Clusters connected subgraphs deterministically and assigns isolated nodes a distinct,
    deterministic cluster identifier.
    """
    if len(G) == 0:
        return {}

    undirected = G.to_undirected()
    connected_nodes = [n for n in undirected.nodes() if undirected.degree(n) > 0]

    # If the graph has no edges at all, all nodes belong to cluster 0
    if not connected_nodes:
        return {n: 0 for n in sorted(G.nodes())}

    subgraph = undirected.subgraph(connected_nodes)

    partition: dict[str, int] = {}
    try:
        raw_communities = nx.algorithms.community.louvain_communities(subgraph, seed=seed)
        # Deterministic sorting: sort nodes within each community, then sort communities by min node id
        sorted_communities = sorted(
            [sorted(c) for c in raw_communities],
            key=lambda c: c[0],
        )
        for cluster_id, comm in enumerate(sorted_communities):
            for node_id in comm:
                partition[node_id] = cluster_id
    except Exception as exc:
        logger.warning("Louvain community detection failed (%s); falling back to connected components", exc)
        components = sorted(
            [sorted(c) for c in nx.connected_components(undirected)],
            key=lambda c: c[0],
        )
        for cluster_id, comp in enumerate(components):
            for node_id in comp:
                partition[node_id] = cluster_id

    # For isolated nodes, assign a separate deterministic cluster ID
    isolated_cluster = max(partition.values()) + 1 if partition else 0
    result: dict[str, int] = {}
    for node in sorted(G.nodes()):
        if node in partition:
            result[node] = partition[node]
        else:
            result[node] = isolated_cluster

    return result


def compute_graph_summary(
    G: nx.DiGraph,
    clusters: dict[str, int],
    pagerank: dict[str, float],
    normalized_centrality: dict[str, float],
    degree_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Synthesize high-level graph statistics and identify top central nodes for frontends."""
    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()

    # Unique clusters
    unique_clusters = set(clusters.values())
    cluster_count = len(unique_clusters)

    # Cluster sizes
    cluster_sizes: dict[str, int] = {}
    for cid in unique_clusters:
        cluster_sizes[str(cid)] = sum(1 for c in clusters.values() if c == cid)

    # Node and edge type distribution
    nodes_by_type: dict[str, int] = {}
    for _, data in G.nodes(data=True):
        ntype = data.get("type", "unknown")
        nodes_by_type[ntype] = nodes_by_type.get(ntype, 0) + 1

    edges_by_type: dict[str, int] = {}
    for _, _, data in G.edges(data=True):
        etype = data.get("type", "unknown")
        edges_by_type[etype] = edges_by_type.get(etype, 0) + 1

    density = round(nx.density(G), 6) if node_count > 1 else 0.0

    is_connected = False
    connected_components_count = 0
    if node_count > 0:
        try:
            is_connected = nx.is_weakly_connected(G)
            connected_components_count = nx.number_weakly_connected_components(G)
        except Exception:
            pass

    # Top central nodes by normalized centrality
    ranked_nodes = sorted(
        G.nodes(data=True),
        key=lambda item: (normalized_centrality.get(item[0], 0.0), pagerank.get(item[0], 0.0)),
        reverse=True,
    )

    top_central_nodes: list[dict[str, Any]] = []
    for nid, data in ranked_nodes[:20]:
        deg = degree_metrics.get(nid, {})
        top_central_nodes.append(
            {
                "id": nid,
                "label": data.get("label", nid),
                "type": data.get("type", "unknown"),
                "path": data.get("path", ""),
                "centrality": normalized_centrality.get(nid, 0.0),
                "pagerank": pagerank.get(nid, 0.0),
                "cluster_id": clusters.get(nid, 0),
                "in_degree": deg.get("in_degree", 0),
                "out_degree": deg.get("out_degree", 0),
            }
        )

    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "cluster_count": cluster_count,
        "density": density,
        "is_connected": is_connected,
        "connected_components_count": connected_components_count,
        "cluster_sizes": cluster_sizes,
        "nodes_by_type": nodes_by_type,
        "edges_by_type": edges_by_type,
        "top_central_nodes": top_central_nodes,
    }


class GraphAnalyticsService:
    """Manages computation, caching, and querying of repository-scoped graph intelligence."""

    def compute_analytics(
        self,
        graph: CodeGraph | dict[str, Any],
        repository_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Compute complete graph intelligence report for a graph instance."""
        G = build_networkx_graph(graph)

        raw_pr, norm_pr = compute_pagerank(G)
        degree_metrics = compute_degree_metrics(G)
        clusters = compute_communities(G)

        summary = compute_graph_summary(
            G=G,
            clusters=clusters,
            pagerank=raw_pr,
            normalized_centrality=norm_pr,
            degree_metrics=degree_metrics,
        )

        # Assemble per-node details
        nodes_list: list[dict[str, Any]] = []
        for nid, data in sorted(G.nodes(data=True), key=lambda x: x[0]):
            deg = degree_metrics.get(nid, {})
            nodes_list.append(
                {
                    "id": nid,
                    "label": data.get("label", nid),
                    "type": data.get("type", "unknown"),
                    "path": data.get("path", ""),
                    "cluster_id": clusters.get(nid, 0),
                    "metrics": {
                        "pagerank": raw_pr.get(nid, 0.0),
                        "normalized_centrality": norm_pr.get(nid, 0.0),
                        "in_degree": deg.get("in_degree", 0),
                        "out_degree": deg.get("out_degree", 0),
                        "degree_centrality": deg.get("degree_centrality", 0.0),
                        "in_degree_centrality": deg.get("in_degree_centrality", 0.0),
                        "out_degree_centrality": deg.get("out_degree_centrality", 0.0),
                    },
                }
            )

        # Group node IDs by cluster
        clusters_grouped: dict[str, list[str]] = {}
        for nid, cid in sorted(clusters.items(), key=lambda x: (x[1], x[0])):
            cid_str = str(cid)
            if cid_str not in clusters_grouped:
                clusters_grouped[cid_str] = []
            clusters_grouped[cid_str].append(nid)

        repo_id_val = repository_id or (
            graph.repository.get("name", "")
            if isinstance(graph, CodeGraph)
            else graph.get("repository", {}).get("name", "")
        )

        return {
            "repository_id": repo_id_val,
            "summary": summary,
            "nodes": nodes_list,
            "clusters": clusters_grouped,
        }

    def enrich_graph_data(
        self,
        graph_data: dict[str, Any],
        analytics: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Enrich a serialized graph dictionary with analytics metadata in place."""
        if analytics is None:
            analytics = self.compute_analytics(graph_data)

        node_metrics_map = {n["id"]: n for n in analytics.get("nodes", [])}

        for node in graph_data.get("nodes", []):
            nid = node.get("id")
            if nid in node_metrics_map:
                n_info = node_metrics_map[nid]
                meta = node.setdefault("metadata", {})
                meta["cluster_id"] = n_info["cluster_id"]
                meta["centrality"] = n_info["metrics"]["normalized_centrality"]
                meta["pagerank"] = n_info["metrics"]["pagerank"]
                meta["in_degree"] = n_info["metrics"]["in_degree"]
                meta["out_degree"] = n_info["metrics"]["out_degree"]
                meta["degree_centrality"] = n_info["metrics"]["degree_centrality"]

        graph_data["analytics"] = analytics.get("summary")
        return graph_data

    def compute_and_save_repository_analytics(
        self,
        repo_id: str,
        code_graph_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        db_path: Optional[Path] = None,
    ) -> dict[str, Any]:
        """Compute analytics for a repository's code_graph.json artifact and persist to disk."""
        artifact_dir = settings.get_repo_artifact_dir(repo_id)
        graph_file = code_graph_path or (artifact_dir / "code_graph.json")
        dest_file = output_path or (artifact_dir / "graph_analytics.json")

        if not graph_file.exists():
            raise FileNotFoundError(
                f"Cannot compute analytics: code graph artifact not found at {graph_file}"
            )

        with open(graph_file, "r", encoding="utf-8") as f:
            graph_data = json.load(f)

        analytics = self.compute_analytics(graph_data, repository_id=repo_id)

        dest_file.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_file, "w", encoding="utf-8") as f:
            json.dump(analytics, f, indent=2)

        logger.info(
            "Saved graph analytics for repository %s (nodes: %d, clusters: %d) to %s",
            repo_id,
            analytics["summary"]["node_count"],
            analytics["summary"]["cluster_count"],
            dest_file,
        )
        return analytics

    def get_repository_analytics(
        self,
        repo_id: str,
        db_path: Optional[Path] = None,
    ) -> dict[str, Any]:
        """Retrieve graph analytics for an indexed repository, computing on demand if necessary."""
        repo = get_repository(repo_id, db_path=db_path)
        if not repo:
            raise FileNotFoundError(f"Repository '{repo_id}' not found")

        if repo.status != "completed":
            raise ValueError(f"Repository indexing is in '{repo.status}' state; graph analytics not ready")

        artifact_dir = settings.get_repo_artifact_dir(repo_id)
        analytics_file = artifact_dir / "graph_analytics.json"
        graph_file = artifact_dir / "code_graph.json"

        # Return cached analytics artifact if available
        if analytics_file.exists():
            with open(analytics_file, "r", encoding="utf-8") as f:
                return json.load(f)

        # Fallback: compute on demand if code_graph.json exists
        if graph_file.exists():
            logger.info("Analytics artifact missing for %s; computing on demand", repo_id)
            return self.compute_and_save_repository_analytics(
                repo_id=repo_id,
                code_graph_path=graph_file,
                output_path=analytics_file,
                db_path=db_path,
            )

        raise FileNotFoundError(f"Code graph artifact not found for repository '{repo_id}'")


# Global service singleton
graph_analytics_service = GraphAnalyticsService()
