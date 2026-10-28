"""Repository-scoped execution workflow detection and tracing service.

Discovers application entry points, traverses static call/import pathways,
validates graph continuity, and synthesizes human-readable lifecycle descriptions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from app.api.schemas import (
    WorkflowItem,
    WorkflowListResponse,
    WorkflowTraceResponse,
)
from app.config import settings
from app.graph.models import (
    EDGE_TYPE_CALLS,
    EDGE_TYPE_DEFINES,
    EDGE_TYPE_IMPORTS,
    NODE_TYPE_FILE,
    NODE_TYPE_FUNCTION,
    NODE_TYPE_METHOD,
)
from app.services.ai_client import ai_client
from app.services.graph_analytics_service import build_networkx_graph
from app.services.repository_graph_cache import repository_graph_cache
from app.storage.repository_store import get_repository

logger = logging.getLogger(__name__)

ENTRY_POINT_FILE_PATTERNS: tuple[str, ...] = (
    "main.py",
    "app.py",
    "server.py",
    "index.js",
    "index.ts",
    "routes/",
    "api/",
    "cli.py",
    "worker.py",
    "handler.py",
)

ENTRY_POINT_NAME_PATTERNS: tuple[str, ...] = (
    "main",
    "run",
    "start",
    "handler",
    "execute",
    "dispatch",
    "app",
    "create_app",
    "init",
)

RELATION_PRIORITY: dict[str, int] = {
    EDGE_TYPE_CALLS: 0,
    EDGE_TYPE_IMPORTS: 1,
    EDGE_TYPE_DEFINES: 2,
    "RENDERS": 1,  # component usage ranks with imports; inheritance is not an execution path
}


class WorkflowService:
    """Manages static workflow discovery, graph path continuity, and persistence."""

    def _get_workflows_file(self, repo_id: str) -> Path:
        """Return the path to the workflows artifact."""
        return settings.get_repo_artifact_dir(repo_id) / "workflows.json"

    def _load_cached_workflows(self, repo_id: str) -> list[WorkflowItem]:
        """Load cached workflows from disk if present."""
        path = self._get_workflows_file(repo_id)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return [WorkflowItem(**w) for w in data]
            except Exception as exc:
                logger.warning("Failed to read cached workflows for %s: %s", repo_id, exc)
        return []

    def _save_cached_workflows(self, repo_id: str, workflows: list[WorkflowItem]) -> None:
        """Persist workflows to disk."""
        path = self._get_workflows_file(repo_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([w.model_dump() for w in workflows], f, indent=2)

    def _get_repository_graphs(
        self,
        repo_id: str,
    ) -> tuple[dict[str, Any], nx.DiGraph]:
        """Load and cache (graph_data, nx_graph) for target repository."""
        repo = get_repository(repo_id)
        if not repo:
            raise FileNotFoundError(f"Repository '{repo_id}' not found")

        if repo.status != "completed":
            raise ValueError(f"Repository indexing is in '{repo.status}' state; workflows not ready")

        cached = repository_graph_cache.get(repo_id)
        if cached:
            return cached

        artifact_dir = settings.get_repo_artifact_dir(repo_id)
        code_graph_file = artifact_dir / "code_graph.json"
        if not code_graph_file.exists():
            raise FileNotFoundError(f"Code graph artifact not found for repository '{repo_id}'")

        with open(code_graph_file, "r", encoding="utf-8") as f:
            graph_data = json.load(f)

        G = build_networkx_graph(graph_data)
        repository_graph_cache.put(repo_id, graph_data, G)
        return graph_data, G

    def _identify_entry_points(
        self,
        G: nx.DiGraph,
        max_entries: int = 5,
        query: Optional[str] = None,
    ) -> list[str]:
        """Identify candidate entry point node IDs matching common entry conventions or queries."""
        query_lower = query.strip().lower() if query else None
        matches: list[str] = []

        if query_lower:
            for nid, data in G.nodes(data=True):
                label = str(data.get("label", "")).lower()
                name = str(data.get("name", "")).lower()
                path = str(data.get("path", "")).lower()
                if query_lower in label or query_lower in name or query_lower in path:
                    matches.append(nid)
            if matches:
                return matches[:max_entries]

        # Prioritize function/method entry points
        func_entries: list[str] = []
        file_entries: list[str] = []
        root_callers: list[str] = []

        for nid, data in G.nodes(data=True):
            ntype = data.get("type", "")
            path = data.get("path", "").lower()
            name = data.get("name", "").lower()

            # Name match (main, run, app, handler, start)
            if ntype in (NODE_TYPE_FUNCTION, NODE_TYPE_METHOD) and any(p == name for p in ENTRY_POINT_NAME_PATTERNS):
                func_entries.append(nid)

            # Path match (app.py, main.py, routes)
            if any(p in path for p in ENTRY_POINT_FILE_PATTERNS):
                file_entries.append(nid)

            # Root callers (out-degree > 0, in-degree == 0)
            if G.out_degree(nid) > 0 and G.in_degree(nid) == 0:
                root_callers.append(nid)

        ordered = func_entries + file_entries + root_callers

        # Fallback to nodes with highest out-degree
        if not ordered:
            sorted_by_out = sorted(G.nodes(), key=lambda n: G.out_degree(n), reverse=True)
            ordered = [n for n in sorted_by_out if G.out_degree(n) > 0]

        # Deduplicate preserving order
        seen: set[str] = set()
        unique_entries: list[str] = []
        for n in ordered:
            if n not in seen and G.has_node(n):
                seen.add(n)
                unique_entries.append(n)
                if len(unique_entries) >= max_entries:
                    break

        return unique_entries

    def _trace_path_from_entry(
        self,
        G: nx.DiGraph,
        entry_node: str,
        max_depth: int = 12,
    ) -> tuple[list[str], list[str]]:
        """Traverse valid outgoing graph edges from an entry point, avoiding cycles."""
        path_nodes: list[str] = []
        path_edges: list[str] = []
        visited: set[str] = set()

        stack: list[tuple[str, int]] = [(entry_node, 0)]

        while stack:
            curr, depth = stack.pop()
            if curr in visited or depth > max_depth:
                continue

            visited.add(curr)
            path_nodes.append(curr)

            # Retrieve outgoing edges sorted by relationship priority
            out_edges: list[tuple[str, str, dict[str, Any]]] = []
            for _, tgt, edata in G.out_edges(curr, data=True):
                if tgt not in visited:
                    out_edges.append((curr, tgt, edata))

            out_edges.sort(
                key=lambda item: RELATION_PRIORITY.get(item[2].get("type", ""), 99)
            )

            for src, tgt, edata in out_edges:
                edge_id = edata.get("id") or f"{src}->{tgt}"
                path_edges.append(edge_id)
                stack.append((tgt, depth + 1))
                break  # Follow top-priority linear branch for clarity

        return path_nodes, path_edges

    async def trace_repository_workflows(
        self,
        repo_id: str,
        max_workflows: int = 5,
        entry_point_query: Optional[str] = None,
        force_refresh: bool = False,
    ) -> WorkflowTraceResponse:
        """Trace static execution pathways starting from candidate entry points."""
        if not force_refresh:
            cached = self._load_cached_workflows(repo_id)
            if cached:
                return WorkflowTraceResponse(
                    repository_id=repo_id,
                    total_workflows=len(cached),
                    workflows=cached,
                )

        graph_data, G = self._get_repository_graphs(repo_id)
        entry_points = self._identify_entry_points(G, max_entries=max_workflows, query=entry_point_query)

        node_map = {n["id"]: n for n in graph_data.get("nodes", [])}
        edge_ids_set = {e["id"] for e in graph_data.get("edges", [])}

        workflows: list[WorkflowItem] = []
        seen_paths: set[tuple[str, ...]] = set()

        for idx, ep in enumerate(entry_points):
            path_nodes, path_edges = self._trace_path_from_entry(G, ep)

            # Must have at least 2 connected components
            if len(path_nodes) < 2:
                continue

            # Ensure all returned node IDs and edge IDs exist in the graph
            valid_nodes = [nid for nid in path_nodes if nid in node_map]
            valid_edges = [eid for eid in path_edges if eid in edge_ids_set]

            if len(valid_nodes) < 2:
                continue

            path_key = tuple(valid_nodes)
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)

            ep_node = node_map.get(ep, {})
            ep_label = ep_node.get("label", ep)
            ep_path = ep_node.get("metadata", {}).get("path") or ep_node.get("metadata", {}).get("file_path", "")

            path_labels = [node_map[nid].get("label", nid) for nid in valid_nodes]

            name, desc = await ai_client.generate_workflow_details(
                entry_label=ep_label,
                entry_path=str(ep_path),
                path_labels=path_labels,
                node_count=len(valid_nodes),
            )

            clean_wf_id = f"wf-{idx+1}-{ep_label.replace('.', '-').replace('()', '').lower()}"

            workflows.append(
                WorkflowItem(
                    id=clean_wf_id,
                    name=name,
                    description=desc,
                    entry_point=ep,
                    ordered_node_ids=valid_nodes,
                    edge_ids=valid_edges,
                    inferred=True,
                )
            )

        self._save_cached_workflows(repo_id, workflows)

        return WorkflowTraceResponse(
            repository_id=repo_id,
            total_workflows=len(workflows),
            workflows=workflows,
        )

    def get_repository_workflows(
        self,
        repo_id: str,
    ) -> WorkflowListResponse:
        """Retrieve detected workflows for a repository."""
        cached = self._load_cached_workflows(repo_id)
        return WorkflowListResponse(
            repository_id=repo_id,
            total_workflows=len(cached),
            workflows=cached,
        )


# Global workflow service singleton
workflow_service = WorkflowService()
