"""Unit tests for LangGraph Q&A Agent and Graph Tools (Phase 3 - Feature A)."""

import pytest

from app.agents.graph_tools import (
    get_cluster_summary,
    get_node_dependencies,
    search_nodes_by_keyword,
)
from app.agents.qa_agent import (
    AgentState,
    answer_codebase_question,
    qa_agent_app,
)
from app.schemas.chat_schema import QAResponse
from app.services.graph_store import get_active_graph_store


def test_graph_store_initialization():
    """Verify default graph store loads and contains nodes from demo galaxy."""
    store = get_active_graph_store()
    assert len(store.graph.nodes) > 0
    assert len(store.nx_graph.nodes) > 0


def test_tool_search_nodes_by_keyword():
    """Verify keyword search returns matching nodes with required schema attributes."""
    matches = search_nodes_by_keyword.invoke({"query": "main"})
    assert isinstance(matches, list)
    assert len(matches) > 0
    first = matches[0]
    assert "id" in first
    assert "label" in first
    assert "type" in first
    assert "path" in first
    assert "centrality" in first
    assert "cluster_id" in first


def test_tool_get_node_dependencies():
    """Verify topological traversal returns inbound and outbound connections."""
    store = get_active_graph_store()
    # Pick first node
    first_node = store.graph.nodes[0]
    deps = get_node_dependencies.invoke({"node_id": first_node.id, "depth": 1})
    assert "node_id" in deps
    assert deps["node_id"] == first_node.id
    assert "inbound_dependencies" in deps
    assert "outbound_dependencies" in deps


def test_tool_get_cluster_summary():
    """Verify cluster summary retrieves PageRank-sorted summary for valid cluster."""
    store = get_active_graph_store()
    first_node = store.graph.nodes[0]
    cid = first_node.position_hint.cluster_id
    summary = get_cluster_summary.invoke({"cluster_id": cid})
    assert isinstance(summary, str)
    assert f"Galaxy Cluster {cid} Profile" in summary
    assert "Key Central Nodes" in summary


@pytest.mark.asyncio
async def test_qa_agent_pipeline_execution():
    """Verify the full LangGraph Q&A StateGraph executes end-to-end and outputs structured response."""
    initial_state: AgentState = {
        "question": "Where is the entry point and how does routing work?",
        "current_node_focus": [],
        "retrieved_context": "",
        "final_answer": "",
        "highlighted_node_ids": [],
    }

    result = await qa_agent_app.ainvoke(initial_state)

    assert "final_answer" in result
    assert len(result["final_answer"]) > 0
    assert "highlighted_node_ids" in result
    assert isinstance(result["highlighted_node_ids"], list)
    assert len(result["highlighted_node_ids"]) > 0


@pytest.mark.asyncio
async def test_answer_codebase_question_helper():
    """Verify answer_codebase_question returns structured QAResponse."""
    response = await answer_codebase_question("Explain the main database or model components.")
    assert isinstance(response, QAResponse)
    assert response.answer
    assert isinstance(response.highlighted_node_ids, list)
