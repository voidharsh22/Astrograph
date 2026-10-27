"""Astrograph AI routes: status, streaming repository chat, and AI-assisted graph features.

All provider access happens server-side with the key from backend/.env. Errors are
returned as ``{"detail": {"code", "message", "retryable"}}`` and never contain secrets.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services import ai_features, graph_insights as gi
from app.services.ai_client import AIError, ai_client, ai_status
from app.services.qa_service import build_chat_messages
from app.services.retrieval import SYSTEM_PROMPT, build_context

logger = logging.getLogger(__name__)

router = APIRouter(tags=["astrograph-ai"])


class AIChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    history: Optional[list[dict[str, str]]] = Field(default=None, max_length=20)
    selected_node_id: Optional[str] = Field(default=None, max_length=500)


class NodeRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=500)


class ImpactRequest(NodeRequest):
    max_depth: int = Field(default=6, ge=1, le=12)


class ArchitectureRequest(BaseModel):
    regenerate: bool = False


class GraphQueryRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


class AdviceRequest(NodeRequest):
    focus: str = Field(default="responsibility", max_length=30)


def _ai_http_error(err: AIError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=err.to_dict())


def _view(repo_id: str) -> gi.RepoView:
    try:
        return gi.load_repo_view(repo_id)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


def _sse(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


@router.get("/ai/status")
def get_ai_status() -> dict[str, Any]:
    """Whether AI is configured, which provider/model is active. Never exposes the key."""
    return ai_status()


@router.post("/repositories/{repository_id}/ai/chat")
async def chat_stream(repository_id: str, req: AIChatRequest) -> StreamingResponse:
    """Stream an answer grounded in the repository analysis (SSE: meta, delta, done, error)."""
    status = ai_status()
    if not status["configured"]:
        raise HTTPException(status_code=503, detail=AIError("ai_not_configured", status["reason"], 503).to_dict())
    view = _view(repository_id)
    bundle = build_context(view, req.question, req.selected_node_id)
    messages = build_chat_messages(req.question, bundle, req.history)

    async def events() -> AsyncIterator[bytes]:
        yield _sse({"type": "meta", "repository": view.repo_name, "repository_id": view.repo_id,
                    "provider": status["provider"], "model": status["model"],
                    "sources": bundle.sources, "highlighted_node_ids": bundle.node_ids,
                    "context_truncated": bundle.truncated})
        try:
            async for delta in ai_client.stream_text(SYSTEM_PROMPT, messages):
                yield _sse({"type": "delta", "text": delta})
            yield _sse({"type": "done"})
        except AIError as err:
            yield _sse({"type": "error", **err.to_dict()})
        except Exception:  # noqa: BLE001 - never leak internals to the stream
            logger.exception("Unexpected AI stream failure")
            yield _sse({"type": "error", "code": "ai_internal", "message": "Unexpected error while generating the answer.", "retryable": True})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/repositories/{repository_id}/insights/health")
def get_health(repository_id: str) -> dict[str, Any]:
    """Deterministic architecture health findings (no AI involved)."""
    return gi.health(_view(repository_id))


@router.get("/repositories/{repository_id}/insights/impact")
def get_impact(repository_id: str, node_id: str, max_depth: int = 6) -> dict[str, Any]:
    """Confirmed reverse-dependency impact of a file or symbol (no AI involved)."""
    try:
        return gi.impact(_view(repository_id), node_id, max(1, min(max_depth, 12)))
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/repositories/{repository_id}/insights/path")
def get_path(repository_id: str, source: str, target: str) -> dict[str, Any]:
    try:
        return gi.shortest_path(_view(repository_id), source, target)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.post("/repositories/{repository_id}/ai/impact")
async def ai_impact(repository_id: str, req: ImpactRequest) -> dict[str, Any]:
    try:
        return await ai_features.impact_assessment(_view(repository_id), req.node_id, req.max_depth)
    except AIError as err:
        raise _ai_http_error(err) from err
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.post("/repositories/{repository_id}/ai/architecture")
async def ai_architecture(repository_id: str, req: ArchitectureRequest) -> dict[str, Any]:
    try:
        return await ai_features.architecture_overview(_view(repository_id), req.regenerate)
    except AIError as err:
        raise _ai_http_error(err) from err


@router.post("/repositories/{repository_id}/ai/onboarding")
async def ai_onboarding(repository_id: str) -> dict[str, Any]:
    try:
        return await ai_features.onboarding(_view(repository_id))
    except AIError as err:
        raise _ai_http_error(err) from err


@router.post("/repositories/{repository_id}/ai/graph-query")
async def ai_graph_query(repository_id: str, req: GraphQueryRequest) -> dict[str, Any]:
    try:
        return await ai_features.interpret_graph_query(_view(repository_id), req.text)
    except AIError as err:
        raise _ai_http_error(err) from err


@router.post("/repositories/{repository_id}/ai/advice")
async def ai_advice(repository_id: str, req: AdviceRequest) -> dict[str, Any]:
    try:
        return await ai_features.node_advice(_view(repository_id), req.node_id, req.focus)
    except AIError as err:
        raise _ai_http_error(err) from err
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
