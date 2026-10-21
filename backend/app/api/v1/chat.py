"""Chat endpoints — semantic codebase Q&A with 3D camera flight targeting."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.agents.qa_agent import answer_codebase_question
from app.schemas.chat_schema import ChatRequest, QAResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=QAResponse,
    summary="Semantic Codebase Q&A with Camera Flight Targeting",
    description=(
        "Ask natural language questions about the codebase architecture, modules, "
        "or execution workflows. The LangGraph agent reasons over the NetworkX graph "
        "topology and returns a structured markdown answer paired with exact "
        "highlighted_node_ids for the 3D frontend to fly the camera towards."
    ),
    responses={
        400: {"description": "Invalid question"},
        500: {"description": "Failed to process Q&A query"},
    },
)
async def chat_codebase(request: ChatRequest) -> QAResponse:
    """Execute the LangGraph Q&A agent over the active codebase graph."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        logger.info("Executing Q&A for query: %s", question)
        response = await answer_codebase_question(question)
        return response
    except Exception as exc:
        logger.exception("Error executing Q&A agent pipeline: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate codebase response: {exc}",
        ) from exc
