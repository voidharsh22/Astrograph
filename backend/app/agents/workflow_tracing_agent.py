"""
Execution Workflow Tracing Agent (Phase 3 - Feature C).

LangGraph agentic pipeline that discovers entry points (FastAPI routers, Next.js page
components, main.py, CLI handlers) and traces logical function calls down the execution
stack to the database/infrastructure layer.

Generates `Workflow` objects matching the JSON contract (`id`, `name`, `description`,
`ordered_node_ids`, `edge_ids`), powering the "Glowing Pulses" animations in the 3D frontend.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.schemas.graph_schema import AstralGraph, GraphNode, Workflow
from app.services.graph_store import GraphStore, get_active_graph_store

logger = logging.getLogger(__name__)

_GEMINI_MODEL = settings.gemini_model


# ---------------------------------------------------------------------------
# LangGraph State Definition
# ---------------------------------------------------------------------------

class WorkflowTraceState(TypedDict):
    """Execution state for the workflow tracing pipeline."""

    graph: AstralGraph
    max_workflows: int
    entry_points: list[GraphNode]
    adjacency: dict[str, list[tuple[str, str, str]]]  # src -> [(target, relation, edge_id)]
    raw_paths: list[tuple[GraphNode, list[str], list[str]]]  # (entry_node, node_ids, edge_ids)
    traced_workflows: list[Workflow]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_gemini_key() -> bool:
    """Check whether a Gemini API key is configured."""
    return bool(
        settings.gemini_api_key
        and settings.gemini_api_key.strip()
        and settings.gemini_api_key != "your-gemini-api-key-here"
    )


_ENTRY_POINT_REGEX = re.compile(
    r"(^|/)(main|app|index|server|cli|__main__|manage|wsgi|asgi|handler|routes|endpoints)\."
    r"(py|js|ts|jsx|tsx|mjs)$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# LangGraph Nodes
# ---------------------------------------------------------------------------

def _node_identify_entry_points(state: WorkflowTraceState) -> dict[str, Any]:
    """
    Step 1: Discover application roots, route files, and high-centrality entry points.
    Build an adjacency lookup from the graph edges.
    """
    graph = state["graph"]
    max_wfs = state.get("max_workflows", 5)

    # Build adjacency: src -> [(target, relation, edge_id)]
    adjacency: dict[str, list[tuple[str, str, str]]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.source, []).append(
            (edge.target, edge.relation.value, edge.id)
        )

    # Identify candidate entry points
    primary_entries: list[GraphNode] = []
    secondary_entries: list[GraphNode] = []

    for node in graph.nodes:
        if node.type.value in ("file", "function"):
            if _ENTRY_POINT_REGEX.search(node.path):
                primary_entries.append(node)
            elif "route" in node.path.lower() or "controller" in node.path.lower():
                secondary_entries.append(node)

    # Fallback to top-centrality nodes if no pattern matches
    if not primary_entries and not secondary_entries:
        sorted_nodes = sorted(
            [n for n in graph.nodes if n.type.value == "file"],
            key=lambda n: n.metrics.centrality,
            reverse=True,
        )
        candidates = sorted_nodes[:max_wfs]
    else:
        candidates = (primary_entries + secondary_entries)[:max_wfs]

    return {
        "entry_points": candidates,
        "adjacency": adjacency,
    }


def _node_trace_paths(state: WorkflowTraceState) -> dict[str, Any]:
    """
    Step 2: Traverses down the execution stack using NetworkX adjacency,
    prioritizing 'calls' > 'imports' > 'contains'.
    """
    entry_points = state.get("entry_points", [])
    adjacency = state.get("adjacency", {})
    graph = state["graph"]
    node_ids = {n.id for n in graph.nodes}

    raw_paths: list[tuple[GraphNode, list[str], list[str]]] = []
    seen_traversals: set[tuple[str, ...]] = set()

    _relation_priority = {"calls": 0, "imports": 1, "contains": 2, "inherits": 3}

    for ep in entry_points:
        visited: set[str] = set()
        path_nodes: list[str] = []
        path_edges: list[str] = []

        stack: list[tuple[str, int]] = [(ep.id, 0)]

        while stack:
            curr, depth = stack.pop()
            if curr in visited or depth > 12:
                continue
            if curr not in node_ids:
                continue

            visited.add(curr)
            path_nodes.append(curr)

            neighbors = adjacency.get(curr, [])
            # Sort neighbors by priority
            sorted_neighbors = sorted(
                neighbors, key=lambda item: _relation_priority.get(item[1], 99)
            )

            for target, _, edge_id in sorted_neighbors:
                if target not in visited and target in node_ids:
                    path_edges.append(edge_id)
                    stack.append((target, depth + 1))

        if len(path_nodes) >= 2:
            path_key = tuple(path_nodes)
            if path_key not in seen_traversals:
                seen_traversals.add(path_key)
                raw_paths.append((ep, path_nodes, path_edges))

    return {"raw_paths": raw_paths}


async def _node_synthesize_workflow_details(state: WorkflowTraceState) -> dict[str, Any]:
    """
    Step 3: Synthesize human-readable workflow names and lifecycle descriptions
    using Gemini (or deterministic heuristics).
    """
    raw_paths = state.get("raw_paths", [])
    graph = state["graph"]
    node_map = {n.id: n for n in graph.nodes}

    workflows: list[Workflow] = []

    if _has_gemini_key():
        try:
            llm = ChatGoogleGenerativeAI(
                model=_GEMINI_MODEL,
                google_api_key=settings.gemini_api_key,
                temperature=0.2,
                max_output_tokens=200,
            )

            async def _name_workflow(
                ep: GraphNode, path_nodes: list[str], path_edges: list[str]
            ) -> Workflow:
                node_labels = [
                    f"{node_map[nid].label} ({node_map[nid].type.value})"
                    for nid in path_nodes[:6]
                    if nid in node_map
                ]
                chain = " -> ".join(node_labels)

                prompt = (
                    f"You are naming an execution workflow in a codebase.\n"
                    f"Entry point: {ep.label} at path '{ep.path}'\n"
                    f"Execution sequence: {chain}\n\n"
                    f"Provide a JSON-compatible output with two lines:\n"
                    f"NAME: [Short 3-5 word name for this workflow, e.g. 'API Request & Handler Pipeline']\n"
                    f"DESC: [1 concise sentence describing what this execution lifecycle accomplishes]"
                )

                resp = await llm.ainvoke([HumanMessage(content=prompt)])
                text = str(resp.content).strip()

                name = f"{ep.label} Execution Flow"
                desc = f"Execution path initiated from {ep.label} across {len(path_nodes)} nodes."

                for line in text.splitlines():
                    if line.startswith("NAME:"):
                        name = line.replace("NAME:", "").strip().strip('"')
                    elif line.startswith("DESC:"):
                        desc = line.replace("DESC:", "").strip().strip('"')

                clean_id = f"wf-{ep.label.replace('.', '-').replace('()', '').lower()}-{len(path_nodes)}"
                return Workflow(
                    id=clean_id,
                    name=name,
                    description=desc,
                    ordered_node_ids=path_nodes,
                    edge_ids=path_edges,
                )

            tasks = [_name_workflow(ep, nodes, edges) for ep, nodes, edges in raw_paths]
            workflows = await asyncio.gather(*tasks)

        except Exception:
            logger.warning("Gemini workflow naming failed; using heuristic naming.", exc_info=True)

    # Heuristic fallback if empty or offline
    if not workflows:
        for ep, path_nodes, path_edges in raw_paths:
            node_labels = [node_map[nid].label for nid in path_nodes[:4] if nid in node_map]
            chain_str = " -> ".join(node_labels)
            clean_id = f"wf-{ep.label.replace('.', '-').replace('()', '').lower()}-{len(path_nodes)}"

            workflows.append(
                Workflow(
                    id=clean_id,
                    name=f"{ep.label} Lifecycle Flow",
                    description=f"Execution pathway starting from {ep.label}: {chain_str} ({len(path_nodes)} nodes)",
                    ordered_node_ids=path_nodes,
                    edge_ids=path_edges,
                )
            )

    return {"traced_workflows": workflows}


def _node_update_graph_workflows(state: WorkflowTraceState) -> dict[str, Any]:
    """Step 4: Save the workflows onto the AstralGraph and sync with the active GraphStore."""
    graph = state["graph"]
    workflows = state.get("traced_workflows", [])

    graph.workflows = workflows

    active_store = get_active_graph_store()
    if active_store and active_store.graph == graph:
        active_store.set_workflows(workflows)

    logger.info("Saved %d traced execution workflows to graph.", len(workflows))
    return {
        "graph": graph,
        "traced_workflows": workflows,
    }


# ---------------------------------------------------------------------------
# LangGraph StateGraph Construction
# ---------------------------------------------------------------------------

def build_workflow_tracing_graph() -> Any:
    """Construct and compile the LangGraph StateGraph for Feature C (Workflow Tracing)."""
    workflow = StateGraph(WorkflowTraceState)

    workflow.add_node("identify_entry_points", _node_identify_entry_points)
    workflow.add_node("trace_paths", _node_trace_paths)
    workflow.add_node("synthesize_details", _node_synthesize_workflow_details)
    workflow.add_node("update_graph_workflows", _node_update_graph_workflows)

    workflow.add_edge(START, "identify_entry_points")
    workflow.add_edge("identify_entry_points", "trace_paths")
    workflow.add_edge("trace_paths", "synthesize_details")
    workflow.add_edge("synthesize_details", "update_graph_workflows")
    workflow.add_edge("update_graph_workflows", END)

    return workflow.compile()


workflow_tracing_app = build_workflow_tracing_graph()


# ---------------------------------------------------------------------------
# Public Execution Helper
# ---------------------------------------------------------------------------

async def trace_codebase_workflows(
    graph: AstralGraph | None = None,
    max_workflows: int = 5,
) -> list[Workflow]:
    """
    Execute the workflow tracing pipeline on the specified or active AstralGraph.

    Returns the list of generated `Workflow` objects.
    """
    target_graph = graph or get_active_graph_store().graph

    initial_state: WorkflowTraceState = {
        "graph": target_graph,
        "max_workflows": max_workflows,
        "entry_points": [],
        "adjacency": {},
        "raw_paths": [],
        "traced_workflows": [],
    }

    result = await workflow_tracing_app.ainvoke(initial_state)
    return result["traced_workflows"]
