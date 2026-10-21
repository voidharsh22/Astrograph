"""Tests for POST /api/v1/chat and LangGraph Q&A State Transitions (Artifact 2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.agents.qa_agent import (
    AgentState,
    _node_generate_answer,
    _node_interpret_query,
    _node_retrieve_topology,
    qa_agent_app,
)
from app.schemas.chat_schema import QAResponse


async def test_chat_empty_question_returns_400(client: AsyncClient) -> None:
    """Chat endpoint rejects empty or whitespace-only questions."""
    resp = await client.post("/api/v1/chat", json={"question": "   "})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


async def test_chat_valid_question_returns_200_and_payload(client: AsyncClient) -> None:
    """Chat endpoint returns 200 with answer and highlighted_node_ids."""
    payload = {"question": "How does routing work and where is the entry point?"}
    resp = await client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert "answer" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0

    assert "highlighted_node_ids" in data
    assert isinstance(data["highlighted_node_ids"], list)
    assert len(data["highlighted_node_ids"]) > 0


@pytest.mark.asyncio
async def test_qa_agent_state_transitions():
    """Verify state transitions step-by-step through each node of the LangGraph StateGraph."""
    initial_state: AgentState = {
        "question": "Where is the API router located?",
        "current_node_focus": [],
        "retrieved_context": "",
        "final_answer": "",
        "highlighted_node_ids": [],
    }

    # Step 1: interpret_query
    s1 = _node_interpret_query(initial_state)
    assert "current_node_focus" in s1
    assert isinstance(s1["current_node_focus"], list)

    merged_state: AgentState = {**initial_state, **s1}  # type: ignore

    # Step 2: retrieve_topology
    s2 = _node_retrieve_topology(merged_state)
    assert "retrieved_context" in s2
    assert isinstance(s2["retrieved_context"], str)

    merged_state = {**merged_state, **s2}  # type: ignore

    # Step 3: generate_answer (heuristic fallback or LLM)
    s3 = await _node_generate_answer(merged_state)
    assert "final_answer" in s3
    assert len(s3["final_answer"]) > 0
    assert "highlighted_node_ids" in s3
    assert isinstance(s3["highlighted_node_ids"], list)


@pytest.mark.asyncio
async def test_qa_agent_with_mocked_gemini_structured_output():
    """Verify with_structured_output path parses structured QAResponse and node IDs correctly."""
    mock_qa_resp = QAResponse(
        answer="The API router is located in `app/api/v1/router.py` and delegates to sub-routers.",
        highlighted_node_ids=["file::app/api/v1/router.py", "file::app/main.py"],
    )

    from unittest.mock import MagicMock

    mock_llm_instance = MagicMock()
    mock_structured_llm = AsyncMock()
    mock_structured_llm.ainvoke.return_value = mock_qa_resp
    mock_llm_instance.with_structured_output.return_value = mock_structured_llm

    state: AgentState = {
        "question": "Where is the router?",
        "current_node_focus": ["file::app/api/v1/router.py"],
        "retrieved_context": "Sample topological context",
        "final_answer": "",
        "highlighted_node_ids": [],
    }

    with patch("app.agents.qa_agent._has_gemini_key", return_value=True):
        with patch("app.agents.qa_agent.ChatGoogleGenerativeAI", return_value=mock_llm_instance):
            result = await _node_generate_answer(state)
            assert result["final_answer"] == mock_qa_resp.answer
            assert result["highlighted_node_ids"] == ["file::app/api/v1/router.py", "file::app/main.py"]
