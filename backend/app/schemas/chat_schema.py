"""Pydantic schemas for the Semantic Codebase Q&A (Feature A)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request payload for POST /api/v1/chat."""

    question: str = Field(
        ...,
        description="User question about the codebase (e.g. 'How does authentication work?')",
        examples=["How does the cartographer parse Python files?"],
    )
    repo_url: str | None = Field(
        None,
        description="Optional repository URL to target. If omitted, uses the currently active or demo graph.",
        examples=["https://github.com/pallets/flask"],
    )


class QAResponse(BaseModel):
    """
    Structured output contract returned by the Q&A Agent and LLM.

    The 3D frontend uses `highlighted_node_ids` to trigger camera flight animations
    to the nodes referenced in `answer`.
    """

    answer: str = Field(
        ...,
        description="Markdown-formatted textual explanation answering the question.",
    )
    highlighted_node_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Exact node IDs referenced in the answer, enabling the 3D frontend "
            "to fly the camera to those specific nodes."
        ),
    )
