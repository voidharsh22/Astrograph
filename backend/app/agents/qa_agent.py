"""
LangGraph Q&A Agent with Camera Flights (Phase 3 - Feature A).

Orchestrates multi-step reasoning and graph traversal using LangGraph and LangChain.
Interprets questions about the codebase, queries the NetworkX graph topology via tools,
and generates structured answers with `highlighted_node_ids` for 3D camera animations.
"""

from __future__ import annotations

import logging
import re
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph

from app.agents.graph_tools import (
    get_cluster_summary,
    get_node_dependencies,
    search_nodes_by_keyword,
)
from app.config import settings
from app.schemas.chat_schema import QAResponse

logger = logging.getLogger(__name__)

_GEMINI_MODEL = "gemini-3.5-flash-lite"


# ---------------------------------------------------------------------------
# LangGraph State Definition
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """
    LangGraph execution state managing the RAG Q&A process.

    Tracks the user question, current nodes of focus, retrieved graph topology context,
    final markdown answer, and node IDs for 3D camera flights.
    """

    question: str
    current_node_focus: list[str]  # IDs of nodes currently being inspected
    retrieved_context: str  # Stringified sub-graphs or file summaries
    final_answer: str
    highlighted_node_ids: list[str]


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


def _extract_keywords(text: str) -> list[str]:
    """Extract candidate keywords and identifiers from a user query."""
    clean = re.sub(r"[^\w\s\.-]", " ", text)
    stopwords = {
        "how", "what", "where", "why", "when", "does", "do", "is", "are", "the",
        "a", "an", "in", "to", "for", "of", "and", "or", "can", "work", "works",
        "explain", "show", "tell", "me", "about", "code", "file", "project",
    }
    words = [w.strip() for w in clean.split() if len(w.strip()) > 2]
    keywords = [w for w in words if w.lower() not in stopwords]
    return keywords or words or [text.strip()]


# ---------------------------------------------------------------------------
# LangGraph Graph Nodes
# ---------------------------------------------------------------------------

def _node_interpret_query(state: AgentState) -> dict[str, Any]:
    """
    Step 1: Parse the user's question, search the graph for candidate nodes,
    and focus on the top relevant nodes.
    """
    question = state.get("question", "")
    keywords = _extract_keywords(question)

    matches: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # Query full question first, then individual keywords
    search_queries = [question] + keywords
    for q in search_queries:
        if not q.strip():
            continue
        nodes = search_nodes_by_keyword.invoke({"query": q})
        for node in nodes:
            nid = node["id"]
            if nid not in seen_ids:
                seen_ids.add(nid)
                matches.append(node)

    # Sort matches by centrality and relevance
    matches.sort(key=lambda n: n.get("centrality", 0.0), reverse=True)
    focused_ids = [n["id"] for n in matches[:5]]

    return {
        "current_node_focus": focused_ids,
    }


def _node_retrieve_topology(state: AgentState) -> dict[str, Any]:
    """
    Step 2: Inspect dependencies and cluster context for the focused nodes
    to assemble rich topological context.
    """
    focused_ids = state.get("current_node_focus", [])
    if not focused_ids:
        # Fallback: search for top entry/core nodes if no nodes found
        fallback_nodes = search_nodes_by_keyword.invoke({"query": "main"})
        focused_ids = [n["id"] for n in fallback_nodes[:3]]

    context_sections: list[str] = []
    seen_clusters: set[int] = set()

    for nid in focused_ids:
        dep_info = get_node_dependencies.invoke({"node_id": nid, "depth": 1})
        if "error" in dep_info:
            continue

        cid = dep_info.get("cluster_id")
        section = [
            f"### Node: `{dep_info.get('label')}` (ID: `{dep_info.get('node_id')}`)",
            f"- **Type**: {dep_info.get('type')}",
            f"- **Path**: `{dep_info.get('path')}`",
            f"- **Centrality**: {dep_info.get('centrality')}",
            f"- **AI Summary**: {dep_info.get('ai_summary') or 'None'}",
        ]

        inbound = dep_info.get("inbound_dependencies", [])
        if inbound:
            section.append(
                "- **Inbound (Called/Imported by)**: "
                + ", ".join(f"`{item.get('label')}` ({item.get('relation')})" for item in inbound[:5])
            )

        outbound = dep_info.get("outbound_dependencies", [])
        if outbound:
            section.append(
                "- **Outbound (Calls/Imports)**: "
                + ", ".join(f"`{item.get('label')}` ({item.get('relation')})" for item in outbound[:5])
            )

        context_sections.append("\n".join(section))

        if cid is not None and cid not in seen_clusters:
            seen_clusters.add(cid)
            cluster_text = get_cluster_summary.invoke({"cluster_id": cid})
            context_sections.append(cluster_text)

    retrieved_context = "\n\n---\n\n".join(context_sections)
    return {
        "current_node_focus": focused_ids,
        "retrieved_context": retrieved_context,
    }


async def _node_generate_answer(state: AgentState) -> dict[str, Any]:
    """
    Step 3: Generate a structured explanation using Gemini with `with_structured_output`,
    guaranteeing a Pydantic `QAResponse` containing `answer` and `highlighted_node_ids`.
    """
    question = state.get("question", "")
    context = state.get("retrieved_context", "")
    focused_ids = state.get("current_node_focus", [])

    if _has_gemini_key():
        try:
            llm = ChatGoogleGenerativeAI(
                model=_GEMINI_MODEL,
                google_api_key=settings.gemini_api_key,
                temperature=0.2,
            )
            structured_llm = llm.with_structured_output(QAResponse)

            system_prompt = (
                "You are Astral Cartographer's Codebase Intelligence Agent. "
                "Your role is to explain architectural mechanisms, components, and execution flows "
                "within the codebase based on the provided topological graph context.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Answer the user's question clearly in concise markdown.\n"
                "2. Identify the EXACT node IDs from the context that are directly relevant to your explanation.\n"
                "3. Return the list of these node IDs in `highlighted_node_ids`. The 3D frontend camera "
                "will smoothly fly to each highlighted node in the visualization.\n"
                "4. Only include node IDs that actually exist in the retrieved graph context."
            )

            user_prompt = (
                f"Question: {question}\n\n"
                f"Retrieved Graph & Codebase Context:\n"
                f"{context if context else 'No specific graph nodes found.'}\n\n"
                f"Candidate Node IDs: {focused_ids}"
            )

            response: QAResponse = await structured_llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )

            return {
                "final_answer": response.answer,
                "highlighted_node_ids": response.highlighted_node_ids or focused_ids,
            }
        except Exception:
            logger.warning("Gemini Q&A call failed; using structured heuristic fallback.", exc_info=True)

    # Deterministic Heuristic Fallback (e.g. offline or no API key)
    answer_lines = [
        f"### Codebase Analysis for: *{question}*\n",
        "Based on the static dependency graph topology and structural indices:",
    ]
    if focused_ids:
        answer_lines.append(f"\nIdentified **{len(focused_ids)}** key architectural node(s):")
        for nid in focused_ids:
            answer_lines.append(f"- Node `{nid}`")
        answer_lines.append(
            "\nThe 3D camera will highlight these nodes and display their dependency connections."
        )
    else:
        answer_lines.append(
            "\nNo direct graph nodes matched the query. Inspecting the root module."
        )

    return {
        "final_answer": "\n".join(answer_lines),
        "highlighted_node_ids": focused_ids,
    }


def _node_finalize(state: AgentState) -> dict[str, Any]:
    """Step 4: Finalize and log completed Q&A execution."""
    logger.info(
        "Q&A pipeline complete. Answer length: %d chars, Highlighted nodes: %d",
        len(state.get("final_answer", "")),
        len(state.get("highlighted_node_ids", [])),
    )
    return {
        "final_answer": state.get("final_answer", ""),
        "highlighted_node_ids": state.get("highlighted_node_ids", []),
    }


# ---------------------------------------------------------------------------
# LangGraph StateGraph Construction
# ---------------------------------------------------------------------------

def build_qa_graph() -> Any:
    """
    Construct and compile the LangGraph StateGraph for Feature A (Q&A).

    Graph Flow:
    START -> interpret_query -> retrieve_topology -> generate_answer -> finalize -> END
    """
    graph = StateGraph(AgentState)

    graph.add_node("interpret_query", _node_interpret_query)
    graph.add_node("retrieve_topology", _node_retrieve_topology)
    graph.add_node("generate_answer", _node_generate_answer)
    graph.add_node("finalize", _node_finalize)

    graph.add_edge(START, "interpret_query")
    graph.add_edge("interpret_query", "retrieve_topology")
    graph.add_edge("retrieve_topology", "generate_answer")
    graph.add_edge("generate_answer", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


# Compiled LangGraph Q&A pipeline instance
qa_agent_app = build_qa_graph()


# ---------------------------------------------------------------------------
# Public Execution Helper
# ---------------------------------------------------------------------------

async def answer_codebase_question(question: str) -> QAResponse:
    """
    Execute the LangGraph Q&A pipeline for a user question.

    Returns a validated `QAResponse` with `answer` and `highlighted_node_ids`.
    """
    initial_state: AgentState = {
        "question": question,
        "current_node_focus": [],
        "retrieved_context": "",
        "final_answer": "",
        "highlighted_node_ids": [],
    }

    result = await qa_agent_app.ainvoke(initial_state)

    return QAResponse(
        answer=result.get("final_answer", ""),
        highlighted_node_ids=result.get("highlighted_node_ids", []),
    )
