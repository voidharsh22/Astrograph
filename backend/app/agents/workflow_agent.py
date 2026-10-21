"""
AI Semantic & Workflow Agent (Phase 3).

Powered by LangGraph and LangChain with Google Gemini (gemini-2.0-flash).

Responsibilities:
- StateGraph-orchestrated workflow execution pipeline.
- Enrich high-centrality graph nodes with AI-generated summaries via LangChain ChatGoogleGenerativeAI.
- Detect and label execution workflow paths through the codebase.
- Graceful degradation: when no API key is configured or the LLM call fails,
  the agent falls back to deterministic heuristic summaries and structural
  workflow detection so the pipeline never breaks.

Usage:
    from app.agents.workflow_agent import enrich_graph
    enriched = await enrich_graph(graph, source_snippets)
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.schemas.graph_schema import AstralGraph, GraphNode, Workflow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Only summarize nodes whose centrality score is at or above this threshold
# to keep API calls (and cost) manageable.
_CENTRALITY_THRESHOLD = 0.15

# Maximum number of nodes to send for AI summarization in a single run.
_MAX_SUMMARIZE_NODES = 40

# Maximum source-code characters sent per node to Gemini.
_MAX_SOURCE_CHARS = 4000

# Gemini model to use for summarization.
_GEMINI_MODEL = settings.gemini_model

# Maximum concurrent Gemini requests.
_MAX_CONCURRENCY = 8


# ---------------------------------------------------------------------------
# LangGraph State Definition
# ---------------------------------------------------------------------------

class WorkflowAgentState(TypedDict):
    """Execution state for the LangGraph workflow pipeline."""
    graph: AstralGraph
    source_snippets: dict[str, str]
    candidates: list[GraphNode]
    summaries: dict[str, str]
    workflows: list[Workflow]


# ---------------------------------------------------------------------------
# LangGraph Nodes
# ---------------------------------------------------------------------------

def _node_select_candidates(state: WorkflowAgentState) -> dict[str, Any]:
    """LangGraph node: identify high-centrality candidate nodes for AI analysis."""
    candidates = _select_candidates(state["graph"], state["source_snippets"])
    return {"candidates": candidates}


async def _node_summarize_nodes(state: WorkflowAgentState) -> dict[str, Any]:
    """LangGraph node: generate AI summaries via LangChain (or fallback heuristics)."""
    graph = state["graph"]
    await _generate_summaries(graph, state["source_snippets"])
    summaries = {n.id: n.ai_summary for n in graph.nodes if n.ai_summary}
    return {"summaries": summaries}


def _node_detect_workflows(state: WorkflowAgentState) -> dict[str, Any]:
    """LangGraph node: trace execution pathways and detect workflows."""
    graph = state["graph"]
    _detect_workflows(graph)
    return {"workflows": graph.workflows}


def _node_finalize(state: WorkflowAgentState) -> dict[str, Any]:
    """LangGraph node: finalize and return enriched graph state."""
    logger.info(
        "LangGraph pipeline complete: %d summaries, %d workflows.",
        len(state.get("summaries", {})),
        len(state.get("workflows", [])),
    )
    return {"graph": state["graph"]}


# ---------------------------------------------------------------------------
# LangGraph StateGraph Construction
# ---------------------------------------------------------------------------

def build_workflow_graph() -> Any:
    """Construct and compile the LangGraph StateGraph pipeline."""
    workflow = StateGraph(WorkflowAgentState)

    workflow.add_node("select_candidates", _node_select_candidates)
    workflow.add_node("summarize_nodes", _node_summarize_nodes)
    workflow.add_node("detect_workflows", _node_detect_workflows)
    workflow.add_node("finalize", _node_finalize)

    workflow.add_edge(START, "select_candidates")
    workflow.add_edge("select_candidates", "summarize_nodes")
    workflow.add_edge("summarize_nodes", "detect_workflows")
    workflow.add_edge("detect_workflows", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile()


# Compiled LangGraph workflow pipeline instance
workflow_agent_app = build_workflow_graph()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def enrich_graph(
    graph: AstralGraph,
    source_snippets: dict[str, str],
) -> AstralGraph:
    """
    Enrich an AstralGraph with AI summaries and detected workflows via LangGraph.

    This is the single entry-point the cartographer calls after building
    the structural graph.

    Args:
        graph: The fully-built AstralGraph (nodes, edges, metrics populated).
        source_snippets: Mapping of node ID -> relevant source code snippet.
                         Only nodes present here *and* above the centrality
                         threshold will be sent to the LLM.

    Returns:
        The same AstralGraph instance, mutated in-place with:
        - ``ai_summary`` populated on qualifying nodes.
        - ``workflows`` populated with detected execution pathways.
    """
    initial_state: WorkflowAgentState = {
        "graph": graph,
        "source_snippets": source_snippets,
        "candidates": [],
        "summaries": {},
        "workflows": [],
    }

    result_state = await workflow_agent_app.ainvoke(initial_state)
    return result_state["graph"]


# ---------------------------------------------------------------------------
# Step 1: Node Summaries
# ---------------------------------------------------------------------------

async def _generate_summaries(
    graph: AstralGraph,
    source_snippets: dict[str, str],
) -> None:
    """Populate ``ai_summary`` on high-centrality nodes."""

    # Select candidate nodes: high centrality + have source code
    candidates = _select_candidates(graph, source_snippets)
    if not candidates:
        logger.info("No candidate nodes for AI summarization.")
        return

    logger.info(
        "Selected %d candidate nodes for summarization (threshold=%.2f).",
        len(candidates),
        _CENTRALITY_THRESHOLD,
    )

    # Build a node-id -> GraphNode lookup for fast mutation
    node_lookup: dict[str, GraphNode] = {n.id: n for n in graph.nodes}

    # Try Gemini via LangChain first; fall back to heuristics
    if _has_gemini_key():
        try:
            summaries = await _summarize_with_gemini(candidates, source_snippets)
            for node_id, summary in summaries.items():
                if node_id in node_lookup:
                    node_lookup[node_id].ai_summary = summary
            logger.info("AI summaries generated for %d nodes via LangChain/Gemini.", len(summaries))
            return
        except Exception:
            logger.warning(
                "LangChain/Gemini summarization failed — falling back to heuristic summaries.",
                exc_info=True,
            )

    # Heuristic fallback (deterministic, zero API calls)
    for node in candidates:
        node_lookup[node.id].ai_summary = _heuristic_summary(
            node, source_snippets.get(node.id, "")
        )
    logger.info("Heuristic summaries generated for %d nodes.", len(candidates))


def _select_candidates(
    graph: AstralGraph,
    source_snippets: dict[str, str],
) -> list[GraphNode]:
    """Return nodes eligible for summarization, sorted by centrality desc."""
    candidates = [
        n
        for n in graph.nodes
        if n.metrics.centrality >= _CENTRALITY_THRESHOLD
        and n.id in source_snippets
    ]
    # Sort by centrality descending so the most important nodes get priority
    candidates.sort(key=lambda n: n.metrics.centrality, reverse=True)
    return candidates[:_MAX_SUMMARIZE_NODES]


def _has_gemini_key() -> bool:
    """Check whether a Gemini API key is configured."""
    return bool(settings.gemini_api_key and settings.gemini_api_key.strip()
                and settings.gemini_api_key != "your-gemini-api-key-here")


# ---------------------------------------------------------------------------
# LangChain-based Gemini summarization
# ---------------------------------------------------------------------------

async def _summarize_with_gemini(
    candidates: list[GraphNode],
    source_snippets: dict[str, str],
) -> dict[str, str]:
    """Send batched summarization requests via LangChain ChatGoogleGenerativeAI."""

    llm = ChatGoogleGenerativeAI(
        model=_GEMINI_MODEL,
        google_api_key=settings.gemini_api_key,
        temperature=0.2,
        max_output_tokens=150,
    )
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _summarize_one(node: GraphNode) -> tuple[str, str]:
        snippet = source_snippets.get(node.id, "")[:_MAX_SOURCE_CHARS]
        prompt = _build_summary_prompt(node, snippet)

        async with semaphore:
            response = await llm.ainvoke([HumanMessage(content=prompt)])

        content = response.content
        if isinstance(content, list):
            text = " ".join(
                item if isinstance(item, str) else str(item.get("text", ""))
                for item in content
            )
        else:
            text = str(content)

        text = text.strip().strip("`").strip('"').strip()
        text = " ".join(text.split())
        if len(text) > 200:
            text = text[:197] + "..."
        return node.id, text

    tasks = [_summarize_one(n) for n in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    summaries: dict[str, str] = {}
    for result in results:
        if isinstance(result, Exception):
            logger.warning("LangChain call failed for one node: %s", result)
            continue
        node_id, summary = result
        if summary:
            summaries[node_id] = summary

    return summaries


def _build_summary_prompt(node: GraphNode, snippet: str) -> str:
    """Construct the summarization prompt for a single node."""
    node_kind = node.type.value  # "file", "function", "class", "directory"
    return (
        f"You are analyzing a codebase for a developer visualization tool.\n"
        f"Below is the source code of a {node_kind} named '{node.label}' "
        f"at path '{node.path}'.\n\n"
        f"```\n{snippet}\n```\n\n"
        f"Write a concise 1-2 sentence summary (under 200 characters) describing "
        f"what this {node_kind} does and its role in the codebase. "
        f"Be specific — mention key responsibilities, patterns, or APIs. "
        f"Do NOT wrap in quotes."
    )


# ---------------------------------------------------------------------------
# Heuristic (fallback) summarization
# ---------------------------------------------------------------------------

def _heuristic_summary(node: GraphNode, source: str) -> str:
    """Generate a deterministic summary from node metadata + source patterns."""
    kind = node.type.value
    label = node.label
    loc = node.metrics.loc

    if kind == "directory":
        return "Directory module containing project source code."

    if kind == "file":
        return _summarize_file_heuristic(label, source, loc)

    if kind == "class":
        return _summarize_class_heuristic(label, source, loc)

    if kind == "function":
        return _summarize_function_heuristic(label, source, loc)

    return f"{kind.capitalize()} '{label}' ({loc} lines)."


def _summarize_file_heuristic(label: str, source: str, loc: int) -> str:
    """Summarize a file by inspecting its top-level patterns."""
    # Look for module docstring
    docstring_match = re.search(r'^"""(.+?)"""', source, re.DOTALL)
    if not docstring_match:
        docstring_match = re.search(r"^'''(.+?)'''", source, re.DOTALL)
    if docstring_match:
        doc = docstring_match.group(1).strip().split("\n")[0].strip()
        if len(doc) > 10:
            return doc[:200]

    # Count structural elements for a generic description
    num_classes = len(re.findall(r"^\s*class\s+\w+", source, re.MULTILINE))
    num_funcs = len(re.findall(r"^\s*(?:def|async\s+def|function|const)\s+\w+", source, re.MULTILINE))

    parts: list[str] = [f"Source file '{label}'"]
    if num_classes:
        parts.append(f"defining {num_classes} class{'es' if num_classes > 1 else ''}")
    if num_funcs:
        parts.append(f"with {num_funcs} function{'s' if num_funcs > 1 else ''}")
    parts.append(f"({loc} lines).")
    return " ".join(parts)


def _summarize_class_heuristic(label: str, source: str, loc: int) -> str:
    """Summarize a class by inspecting its docstring or method count."""
    pattern = rf'class\s+{re.escape(label)}[^:]*:\s*(?:#[^\n]*)?\s*"""(.+?)"""'
    match = re.search(pattern, source, re.DOTALL)
    if match:
        doc = match.group(1).strip().split("\n")[0].strip()
        if len(doc) > 10:
            return doc[:200]

    num_methods = len(re.findall(r"^\s+(?:def|async\s+def)\s+\w+", source, re.MULTILINE))
    return f"Class '{label}' with {num_methods} method{'s' if num_methods != 1 else ''} ({loc} lines)."


def _summarize_function_heuristic(label: str, source: str, loc: int) -> str:
    """Summarize a function from its docstring."""
    clean_label = label.rstrip("()")
    pattern = rf'def\s+{re.escape(clean_label)}\s*\([^)]*\)[^:]*:\s*(?:#[^\n]*)?\s*"""(.+?)"""'
    match = re.search(pattern, source, re.DOTALL)
    if match:
        doc = match.group(1).strip().split("\n")[0].strip()
        if len(doc) > 10:
            return doc[:200]

    return f"Function '{clean_label}' ({loc} lines)."


# ---------------------------------------------------------------------------
# Step 2: Workflow Detection
# ---------------------------------------------------------------------------

def _detect_workflows(graph: AstralGraph) -> None:
    """
    Detect execution workflows by tracing paths from entry-point nodes.

    Strategy:
    1. Identify entry-point nodes (main.py, app.py, index.js, routes, handlers).
    2. Build an adjacency map from edges (imports / calls / contains).
    3. BFS/DFS from each entry point, collecting the traversal as a workflow.
    """
    adjacency: dict[str, list[tuple[str, str, str]]] = {}  # src -> [(tgt, relation, edge_id)]
    for edge in graph.edges:
        adjacency.setdefault(edge.source, []).append(
            (edge.target, edge.relation.value, edge.id)
        )

    node_ids = {n.id for n in graph.nodes}
    node_lookup: dict[str, GraphNode] = {n.id: n for n in graph.nodes}

    entry_points = _find_entry_points(graph)

    workflows: list[Workflow] = []
    seen_paths: set[tuple[str, ...]] = set()

    for ep_node in entry_points:
        path_nodes, path_edges = _trace_workflow(ep_node.id, adjacency, node_ids)

        if len(path_nodes) < 2:
            continue

        path_key = tuple(path_nodes)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)

        wf_name = _workflow_name(ep_node, path_nodes, node_lookup)
        wf_id = f"wf-{ep_node.id.replace('::', '-').replace('/', '-')}"

        workflows.append(
            Workflow(
                id=wf_id,
                name=wf_name,
                description=_workflow_description(ep_node, path_nodes, node_lookup),
                ordered_node_ids=path_nodes,
                edge_ids=path_edges,
            )
        )

    graph.workflows = workflows
    logger.info("Detected %d execution workflows.", len(workflows))


# ---------------------------------------------------------------------------
# Workflow helpers
# ---------------------------------------------------------------------------

_ENTRY_POINT_PATTERNS = re.compile(
    r"(^|/)(main|app|index|server|cli|__main__|manage|wsgi|asgi|handler|lambda_function)\."
    r"(py|js|ts|jsx|tsx|mjs)$",
    re.IGNORECASE,
)

_ROUTE_PATTERNS = re.compile(
    r"(route|endpoint|view|controller|handler|api)",
    re.IGNORECASE,
)


def _find_entry_points(graph: AstralGraph) -> list[GraphNode]:
    """Identify entry-point nodes: files whose names indicate application roots or route layers."""
    entry_points: list[GraphNode] = []
    fallback: list[GraphNode] = []

    for node in graph.nodes:
        if node.type.value != "file":
            continue

        if _ENTRY_POINT_PATTERNS.search(node.path):
            entry_points.append(node)
        elif _ROUTE_PATTERNS.search(node.path):
            fallback.append(node)

    if not entry_points:
        entry_points = fallback

    if not entry_points:
        file_nodes = [n for n in graph.nodes if n.type.value == "file"]
        file_nodes.sort(key=lambda n: n.metrics.centrality, reverse=True)
        entry_points = file_nodes[:3]

    return entry_points


def _trace_workflow(
    start_id: str,
    adjacency: dict[str, list[tuple[str, str, str]]],
    node_ids: set[str],
    max_depth: int = 15,
) -> tuple[list[str], list[str]]:
    """
    DFS traversal from ``start_id`` following import and call edges.

    Returns (ordered_node_ids, traversed_edge_ids).
    Prioritises 'calls' > 'imports' > 'contains' edges and avoids cycles.
    """
    visited: set[str] = set()
    path_nodes: list[str] = []
    path_edges: list[str] = []

    stack: list[tuple[str, int]] = [(start_id, 0)]
    _priority = {"calls": 0, "imports": 1, "contains": 2, "inherits": 3}

    while stack:
        current, depth = stack.pop()

        if current in visited or depth > max_depth:
            continue
        if current not in node_ids:
            continue

        visited.add(current)
        path_nodes.append(current)

        neighbors = adjacency.get(current, [])
        neighbors_sorted = sorted(neighbors, key=lambda x: _priority.get(x[1], 99))

        for target, relation, edge_id in neighbors_sorted:
            if target not in visited and target in node_ids:
                path_edges.append(edge_id)
                stack.append((target, depth + 1))

    return path_nodes, path_edges


def _workflow_name(
    entry_node: GraphNode,
    path_nodes: list[str],
    node_lookup: dict[str, GraphNode],
) -> str:
    """Build a human-readable workflow name."""
    label = entry_node.label
    depth = len(path_nodes)
    return f"{label} → execution flow ({depth} nodes)"


def _workflow_description(
    entry_node: GraphNode,
    path_nodes: list[str],
    node_lookup: dict[str, GraphNode],
) -> str:
    """Build a workflow description showing the key traversal."""
    labels: list[str] = []
    for nid in path_nodes[:5]:
        if nid in node_lookup:
            labels.append(node_lookup[nid].label)

    chain = " → ".join(labels)
    if len(path_nodes) > 5:
        chain += f" → ... ({len(path_nodes) - 5} more)"

    return f"Execution pathway starting from {entry_node.label}: {chain}"
