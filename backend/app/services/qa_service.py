"""Repository-scoped codebase Q&A grounded in the persisted analysis.

Both the JSON ``/chat`` route and the streaming ``/ai/chat`` route use the same
retrieval layer. When AI is unavailable an :class:`AIError` propagates; no
placeholder answer is ever produced.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from app.api.schemas import QAResponse
from app.services.ai_client import ai_client, ai_status
from app.services.graph_insights import file_path, load_repo_view
from app.services.retrieval import SYSTEM_PROMPT, ContextBundle, build_context, wrap_context

MAX_HISTORY_TURNS = 10
MAX_TURN_CHARS = 4000


def clean_history(history: Optional[list[dict[str, str]]]) -> list[dict[str, str]]:
    out = []
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = "assistant" if turn.get("role") in ("assistant", "model") else "user"
        content = str(turn.get("content", ""))[:MAX_TURN_CHARS]
        if content.strip():
            out.append({"role": role, "content": content})
    return out


def build_chat_messages(
    question: str, bundle: ContextBundle, history: Optional[list[dict[str, str]]]
) -> list[dict[str, str]]:
    msgs = clean_history(history)
    # Gemini/Claude require alternating roles starting with user; merge if needed.
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    msgs.append({"role": "user", "content": f"{wrap_context(bundle)}\n\nQuestion: {question}"})
    return msgs


class QAService:
    async def answer_question(
        self,
        repo_id: str,
        question: str,
        history: Optional[list[dict[str, str]]] = None,
        selected_node_id: Optional[str] = None,
    ) -> QAResponse:
        start = time.perf_counter()
        view = load_repo_view(repo_id)
        bundle = build_context(view, question, selected_node_id)
        answer = await ai_client.complete_text(SYSTEM_PROMPT, build_chat_messages(question, bundle, history), temperature=0.2)
        return QAResponse(
            repository_id=repo_id,
            question=question,
            answer=answer,
            highlighted_node_ids=bundle.node_ids,
            relevant_files=[s["path"] for s in bundle.sources],
            relevant_symbols=[],
            generation_duration_ms=round((time.perf_counter() - start) * 1000, 2),
            model=str(ai_status().get("model")),
        )


qa_service = QAService()
