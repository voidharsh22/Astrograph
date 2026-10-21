"""
Galaxy (Module) Summarization Agent (Phase 3 - Feature B).

A LangGraph batch workflow that uses Louvain community detection clusters from the
NetworkX graph. For each cluster, it aggregates the AI summaries and topological roles
of the top 3-5 most central nodes (PageRank) and synthesizes a high-level "Galaxy Summary"
displayed in the 3D frontend when zooming out.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.schemas.graph_schema import AstralGraph, GraphNode
from app.services.graph_store import GraphStore, get_active_graph_store

logger = logging.getLogger(__name__)

_GEMINI_MODEL = settings.gemini_model
_MAX_CONCURRENCY = 5


# ---------------------------------------------------------------------------
# LangGraph State Definition
# ---------------------------------------------------------------------------

class ClusterAgentState(TypedDict):
    """Execution state for the Galaxy cluster summarization LangGraph pipeline."""

    graph: AstralGraph
    clusters_data: dict[int, list[dict[str, Any]]]
    cluster_summaries: dict[int, str]


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


# ---------------------------------------------------------------------------
# LangGraph Nodes
# ---------------------------------------------------------------------------

def _node_extract_clusters(state: ClusterAgentState) -> dict[str, Any]:
    """
    Step 1: Group nodes by Louvain cluster_id, rank by PageRank centrality,
    and extract top 3-5 central nodes per cluster.
    """
    graph = state["graph"]
    clusters_data: dict[int, list[dict[str, Any]]] = {}

    grouped_nodes: dict[int, list[GraphNode]] = {}
    for node in graph.nodes:
        cid = node.position_hint.cluster_id
        grouped_nodes.setdefault(cid, []).append(node)

    for cid, nodes in grouped_nodes.items():
        # Sort descending by centrality
        sorted_nodes = sorted(nodes, key=lambda n: n.metrics.centrality, reverse=True)
        top_nodes = sorted_nodes[:5]

        clusters_data[cid] = [
            {
                "id": n.id,
                "label": n.label,
                "type": n.type.value,
                "path": n.path,
                "centrality": n.metrics.centrality,
                "summary": n.ai_summary or "",
            }
            for n in top_nodes
        ]

    return {"clusters_data": clusters_data}


async def _node_synthesize_summaries(state: ClusterAgentState) -> dict[str, Any]:
    """
    Step 2: Synthesize a single high-level Galaxy Summary for each cluster using Gemini,
    with deterministic heuristic fallback.
    """
    clusters_data = state["clusters_data"]
    summaries: dict[int, str] = {}

    if _has_gemini_key():
        try:
            llm = ChatGoogleGenerativeAI(
                model=_GEMINI_MODEL,
                google_api_key=settings.gemini_api_key,
                temperature=0.2,
                max_output_tokens=150,
            )
            semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

            async def _summarize_one(cid: int, top_nodes: list[dict[str, Any]]) -> tuple[int, str]:
                nodes_desc = "\n".join(
                    f"- {n['label']} ({n['type']} at `{n['path']}`, centrality: {n['centrality']}): {n['summary'] or 'core module'}"
                    for n in top_nodes
                )
                system_prompt = (
                    "You are a software architect summarizing high-level module clusters in a 3D codebase visualizer.\n"
                    "Provide a concise, 1-sentence Galaxy Summary (max 100 characters) describing "
                    "the core domain/functional responsibility of this cluster. "
                    "Example: 'Core routing, request logging, and authentication middleware.' "
                    "Do NOT wrap in quotes."
                )
                user_prompt = (
                    f"Cluster ID: {cid}\n"
                    f"Top central nodes:\n{nodes_desc}\n\n"
                    f"Galaxy Summary:"
                )

                async with semaphore:
                    resp = await llm.ainvoke(
                        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    )

                text = str(resp.content).strip().strip('"').strip("'").strip()
                if len(text) > 120:
                    text = text[:117] + "..."
                return cid, text

            tasks = [_summarize_one(cid, nodes) for cid, nodes in clusters_data.items()]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for item in results:
                if isinstance(item, tuple):
                    cid, summary = item
                    if summary:
                        summaries[cid] = summary

        except Exception:
            logger.warning("Gemini cluster summarization failed; using heuristic fallback.", exc_info=True)

    # Fill any remaining clusters with heuristic summaries
    for cid, top_nodes in clusters_data.items():
        if cid not in summaries:
            summaries[cid] = _heuristic_cluster_summary(cid, top_nodes)

    return {"cluster_summaries": summaries}


def _heuristic_cluster_summary(cid: int, top_nodes: list[dict[str, Any]]) -> str:
    """Generate a deterministic high-level cluster summary from paths and labels."""
    if not top_nodes:
        return f"Galaxy module {cid} containing general application logic."

    paths = {n["path"].split("/")[0] for n in top_nodes if "/" in n["path"]}
    path_prefix = "/".join(sorted(paths)[:2]) if paths else "core"

    labels = [n["label"].replace("()", "") for n in top_nodes[:3]]
    labels_str = ", ".join(labels)

    return f"Galaxy module for '{path_prefix}' coordinating {labels_str}."


def _node_update_graph(state: ClusterAgentState) -> dict[str, Any]:
    """
    Step 3: Mutate the AstralGraph metadata with the cluster summaries and update
    the active in-memory GraphStore.
    """
    graph = state["graph"]
    summaries = state["cluster_summaries"]

    graph.metadata.cluster_summaries.update(summaries)

    # Sync with global active store
    active_store = get_active_graph_store()
    if active_store and active_store.graph == graph:
        active_store.set_cluster_summaries(summaries)

    logger.info("Galaxy cluster summarization complete for %d clusters.", len(summaries))
    return {
        "graph": graph,
        "cluster_summaries": summaries,
    }


# ---------------------------------------------------------------------------
# LangGraph StateGraph Construction
# ---------------------------------------------------------------------------

def build_cluster_agent_graph() -> Any:
    """Construct and compile the LangGraph StateGraph for Feature B (Cluster Summarization)."""
    workflow = StateGraph(ClusterAgentState)

    workflow.add_node("extract_clusters", _node_extract_clusters)
    workflow.add_node("synthesize_summaries", _node_synthesize_summaries)
    workflow.add_node("update_graph", _node_update_graph)

    workflow.add_edge(START, "extract_clusters")
    workflow.add_edge("extract_clusters", "synthesize_summaries")
    workflow.add_edge("synthesize_summaries", "update_graph")
    workflow.add_edge("update_graph", END)

    return workflow.compile()


cluster_agent_app = build_cluster_agent_graph()


# ---------------------------------------------------------------------------
# Public Execution Helper
# ---------------------------------------------------------------------------

async def summarize_galaxy_clusters(graph: AstralGraph | None = None) -> dict[int, str]:
    """
    Execute the cluster summarization workflow on the specified or active AstralGraph.

    Returns a dictionary of cluster_id -> high-level Galaxy Summary string.
    """
    target_graph = graph or get_active_graph_store().graph

    initial_state: ClusterAgentState = {
        "graph": target_graph,
        "clusters_data": {},
        "cluster_summaries": {},
    }

    result = await cluster_agent_app.ainvoke(initial_state)
    return result["cluster_summaries"]
