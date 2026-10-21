"""
Graph traversal and query operations for Astral Cartographer's code graphs.
Provides dependency queries, caller/callee searches, and blast radius impact analysis.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Optional

from app.schemas.graph_schema import AstralGraph, GraphNode


def get_dependencies_for_node(
    graph: AstralGraph,
    node_id: str,
    direction: str = "outgoing",  # "outgoing" | "incoming" | "both"
    depth: int = 1,
) -> dict[str, Any]:
    """Retrieve incoming or outgoing dependencies for a node up to specified depth."""
    node_map = {n.id: n for n in graph.nodes}
    if node_id not in node_map:
        return {"root_node_id": node_id, "found": False, "nodes": [], "edges": []}

    visited_nodes: set[str] = {node_id}
    result_edges: list[dict[str, Any]] = []

    # BFS queue: (current_node_id, current_depth)
    queue: deque[tuple[str, int]] = deque([(node_id, 0)])

    while queue:
        curr_id, curr_depth = queue.popleft()
        if curr_depth >= depth:
            continue

        for edge in graph.edges:
            if direction in ("outgoing", "both") and edge.source == curr_id:
                target_id = edge.target
                result_edges.append(edge.model_dump())
                if target_id not in visited_nodes:
                    visited_nodes.add(target_id)
                    queue.append((target_id, curr_depth + 1))

            if direction in ("incoming", "both") and edge.target == curr_id:
                source_id = edge.source
                result_edges.append(edge.model_dump())
                if source_id not in visited_nodes:
                    visited_nodes.add(source_id)
                    queue.append((source_id, curr_depth + 1))

    return {
        "root_node_id": node_id,
        "found": True,
        "direction": direction,
        "depth": depth,
        "nodes": [node_map[nid].model_dump() for nid in visited_nodes if nid in node_map],
        "edges": result_edges,
    }


def compute_impact_analysis(
    graph: AstralGraph,
    target_node_id: str,
    max_depth: int = 3,
) -> dict[str, Any]:
    """Compute the architectural blast radius of modifying a node (downstream callers & importers)."""
    node_map = {n.id: n for n in graph.nodes}
    if target_node_id not in node_map:
        return {"target_id": target_node_id, "found": False, "impacted_count": 0, "impacted_nodes": []}

    # Follow incoming CALLS and IMPORTS edges (who calls or imports this node?)
    visited: set[str] = {target_node_id}
    queue: deque[tuple[str, int]] = deque([(target_node_id, 0)])
    impact_levels: dict[str, int] = {target_node_id: 0}

    while queue:
        curr_id, curr_depth = queue.popleft()
        if curr_depth >= max_depth:
            continue

        for edge in graph.edges:
            # If curr_id is called or imported by edge.source
            if edge.target == curr_id and edge.relation.value in ("calls", "imports", "inherits"):
                caller_id = edge.source
                if caller_id not in visited:
                    visited.add(caller_id)
                    impact_levels[caller_id] = curr_depth + 1
                    queue.append((caller_id, curr_depth + 1))

    impacted_nodes = [
        {
            **node_map[nid].model_dump(),
            "impact_distance": impact_levels.get(nid, 0),
        }
        for nid in visited
        if nid != target_node_id and nid in node_map
    ]

    return {
        "target_id": target_node_id,
        "found": True,
        "max_depth": max_depth,
        "impacted_count": len(impacted_nodes),
        "impacted_nodes": sorted(impacted_nodes, key=lambda x: x["impact_distance"]),
    }
