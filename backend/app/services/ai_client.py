"""Provider-aware LLM client for Astrograph (Gemini or Anthropic Claude).

The provider and key come from the backend environment (``backend/.env``). The key
is only ever used server-side, is never logged or returned, and is scrubbed from
every error message. When AI is unavailable the client raises :class:`AIError`
with an actionable code; it never fabricates an answer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GEMINI_API_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"
ANTHROPIC_URL: str = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION: str = "2023-06-01"
MAX_RETRIES: int = 2
MAX_CONCURRENT_REQUESTS: int = 4

_PLACEHOLDER = re.compile(r"^(your[-_ ]|changeme|xxx|<)", re.IGNORECASE)


class AIError(Exception):
    """Structured AI failure that routes can return to the client verbatim."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 502,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


def _valid_key(key: str) -> bool:
    key = (key or "").strip()
    return len(key) > 8 and not _PLACEHOLDER.match(key)


def _key_for(provider: str) -> str:
    return (settings.gemini_api_key if provider == "gemini" else settings.anthropic_api_key).strip()


def _model_for(provider: str) -> str:
    return settings.gemini_model if provider == "gemini" else settings.anthropic_model


def configured_provider() -> Optional[str]:
    """Return the active provider name, or None when no usable key is configured."""
    preferred = settings.ai_provider
    order = [preferred] if preferred in ("gemini", "anthropic") else []
    order += [p for p in ("gemini", "anthropic") if p not in order]
    for provider in order:
        if _valid_key(_key_for(provider)):
            return provider
    return None


def has_gemini_key() -> bool:
    return _valid_key(settings.gemini_api_key)


def ai_status() -> dict[str, Any]:
    """Report availability without exposing any secret."""
    provider = configured_provider()
    if provider is None:
        return {
            "configured": False,
            "provider": None,
            "model": None,
            "reason": "No AI key found. Set GEMINI_API_KEY (or ANTHROPIC_API_KEY) in backend/.env and restart the backend.",
        }
    return {"configured": True, "provider": provider, "model": _model_for(provider), "reason": None}


def _scrub(text: str) -> str:
    """Remove any configured key from text before it is logged or returned."""
    for key in (settings.gemini_api_key, settings.anthropic_api_key):
        key = (key or "").strip()
        if key and len(key) > 8:
            text = text.replace(key, "[redacted]")
    return text[:500]


def _error_from_response(provider: str, status: int, body: bytes, retry_after: Optional[str]) -> AIError:
    detail = ""
    try:
        parsed = json.loads(body or b"{}")
        err = parsed.get("error", parsed)
        detail = err.get("message", "") if isinstance(err, dict) else str(err)
    except Exception:  # noqa: BLE001 - best-effort parse of provider error body
        detail = ""
    detail = _scrub(detail)
    lowered = detail.lower()
    name = "Gemini" if provider == "gemini" else "Claude"

    if status in (401, 403) or "api key not valid" in lowered or "api_key_invalid" in lowered:
        return AIError(
            "ai_key_rejected",
            f"The {name} API key in backend/.env was rejected by the provider. Check that it is valid and has access to model '{_model_for(provider)}'.",
            status_code=502,
        )
    if status == 429 or "resource_exhausted" in lowered or "quota" in lowered or "rate limit" in lowered:
        wait = f" Retry in about {retry_after}s." if retry_after and retry_after.isdigit() else ""
        if "quota" in lowered or "billing" in lowered or "credit" in lowered:
            return AIError(
                "ai_quota_exceeded",
                f"The {name} quota or credits for this key are exhausted. Check the provider's billing/usage page.",
                status_code=429,
            )
        return AIError("ai_rate_limited", f"The {name} API is rate limiting requests.{wait}", 429, True)
    if status == 402 or "credit balance" in lowered or "billing" in lowered:
        return AIError(
            "ai_quota_exceeded",
            f"The {name} account has no remaining credits. Add credits or use another key.",
            status_code=402,
        )
    if status == 404:
        return AIError(
            "ai_model_not_found",
            f"Model '{_model_for(provider)}' was not found for {name}. Fix GEMINI_MODEL/ANTHROPIC_MODEL in backend/.env.",
            status_code=502,
        )
    if status == 400:
        return AIError("ai_bad_request", f"{name} rejected the request: {detail or 'bad request'}", 502)
    if status >= 500:
        return AIError("ai_provider_unavailable", f"{name} is temporarily unavailable (HTTP {status}).", 502, True)
    return AIError("ai_provider_error", f"{name} returned HTTP {status}. {detail}".strip(), 502)


Message = dict[str, str]  # {"role": "user"|"assistant", "content": str}


class AIClient:
    """Streams or completes chat requests against the configured provider."""

    def __init__(self) -> None:
        self._semaphore: Optional[asyncio.Semaphore] = None

    def _sem(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        return self._semaphore

    # ------------------------------------------------------------------ requests
    def _gemini_request(
        self, system: str, messages: list[Message], max_tokens: int, temperature: float, json_mode: bool
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = f"{GEMINI_API_URL}/{settings.gemini_model}:streamGenerateContent?alt=sse"
        headers = {"x-goog-api-key": settings.gemini_api_key.strip(), "Content-Type": "application/json"}
        generation: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            generation["responseMimeType"] = "application/json"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in messages
            ],
            "generationConfig": generation,
        }
        return url, headers, payload

    def _anthropic_request(
        self, system: str, messages: list[Message], max_tokens: int, temperature: float
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        headers = {
            "x-api-key": settings.anthropic_api_key.strip(),
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": settings.anthropic_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": messages,
            "stream": True,
        }
        return ANTHROPIC_URL, headers, payload

    @staticmethod
    def _gemini_text(event: dict[str, Any]) -> str:
        feedback = event.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise AIError(
                "ai_blocked",
                f"Gemini blocked the request ({feedback['blockReason']}). Try rephrasing the question.",
                422,
            )
        out = []
        for cand in event.get("candidates", [])[:1]:
            for part in (cand.get("content") or {}).get("parts", []):
                if isinstance(part.get("text"), str):
                    out.append(part["text"])
        return "".join(out)

    async def _stream_once(
        self, provider: str, system: str, messages: list[Message], max_tokens: int, temperature: float, json_mode: bool
    ) -> AsyncIterator[str]:
        if provider == "gemini":
            url, headers, payload = self._gemini_request(system, messages, max_tokens, temperature, json_mode)
        else:
            url, headers, payload = self._anthropic_request(system, messages, max_tokens, temperature)
        timeout = httpx.Timeout(settings.ai_timeout_seconds, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise _error_from_response(provider, resp.status_code, body, resp.headers.get("retry-after"))
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if provider == "gemini":
                            text = self._gemini_text(event)
                        elif event.get("type") == "content_block_delta":
                            text = (event.get("delta") or {}).get("text", "")
                        elif event.get("type") == "error":
                            raise AIError(
                                "ai_provider_error",
                                _scrub((event.get("error") or {}).get("message", "Claude stream error")),
                                502,
                                True,
                            )
                        else:
                            text = ""
                        if text:
                            yield text
        except httpx.TimeoutException as exc:
            raise AIError("ai_timeout", "The AI provider did not respond in time. Try again.", 504, True) from exc
        except httpx.HTTPError as exc:
            raise AIError(
                "ai_unreachable",
                f"Could not reach the AI provider from the Astrograph backend ({type(exc).__name__}).",
                502,
                True,
            ) from exc

    async def stream_text(
        self,
        system: str,
        messages: list[Message],
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> AsyncIterator[str]:
        """Yield text deltas. Retries transient failures only before any text was emitted."""
        provider = configured_provider()
        if provider is None:
            raise AIError("ai_not_configured", ai_status()["reason"], 503)
        limit = max_tokens or settings.ai_max_output_tokens
        attempt = 0
        async with self._sem():
            while True:
                emitted = False
                try:
                    async for delta in self._stream_once(provider, system, messages, limit, temperature, json_mode):
                        emitted = True
                        yield delta
                    return
                except AIError as err:
                    if emitted or not err.retryable or attempt >= MAX_RETRIES:
                        raise
                    attempt += 1
                    await asyncio.sleep(0.6 * (2 ** (attempt - 1)))
                    logger.warning("Retrying AI request (%s), attempt %d", err.code, attempt)

    async def complete_text(
        self,
        system: str,
        messages: list[Message],
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        parts: list[str] = []
        async for delta in self.stream_text(system, messages, max_tokens, temperature, json_mode):
            parts.append(delta)
        text = "".join(parts).strip()
        if not text:
            raise AIError("ai_empty_response", "The AI provider returned an empty response. Try again.", 502, True)
        return text

    async def complete_json(
        self, system: str, messages: list[Message], max_tokens: Optional[int] = None
    ) -> dict[str, Any]:
        """Complete and parse a JSON object response; raises AIError when it cannot be parsed."""
        text = await self.complete_text(system, messages, max_tokens, temperature=0.1, json_mode=True)
        return parse_json_object(text)

    # --------------------------------------------- labels used by clusters/workflows
    async def generate_cluster_summary(
        self,
        cluster_id: int,
        top_nodes: list[dict[str, Any]],
        languages: list[str],
        paths: list[str],
    ) -> str:
        """One-sentence cluster label; deterministic structural label when AI is unavailable."""
        nodes_desc = "\n".join(
            f"- {n.get('label', n.get('id'))} ({n.get('type')} at `{n.get('path')}`)" for n in top_nodes[:5]
        )
        system = (
            "You label module clusters in a code graph. Reply with ONE sentence (max 100 characters) "
            "describing the cluster's responsibility, using only the names given. No quotes."
        )
        prompt = (
            f"Cluster {cluster_id}\nPaths: {', '.join(paths) if paths else 'root'}\n"
            f"Languages: {', '.join(languages) or 'unknown'}\nTop nodes:\n{nodes_desc}"
        )
        try:
            raw = await self.complete_text(system, [{"role": "user", "content": prompt}], max_tokens=120)
            clean = raw.strip().strip('"').strip("'").strip()
            return clean if len(clean) <= 130 else clean[:127] + "..."
        except AIError as err:
            logger.info("Cluster summary falling back to structural label (%s)", err.code)
        primary_dir = paths[0] if paths else "root"
        labels = ", ".join(n.get("label", n.get("id", "")) for n in top_nodes[:3]) or "components"
        return f"Structural cluster for '{primary_dir}' containing {labels}."

    async def generate_workflow_details(
        self,
        entry_label: str,
        entry_path: str,
        path_labels: list[str],
        node_count: int,
    ) -> tuple[str, str]:
        """Workflow name/description; deterministic structural text when AI is unavailable."""
        chain = " -> ".join(path_labels[:6])
        system = (
            "You name statically inferred workflows from call/import graphs. Output exactly two lines:\n"
            "NAME: <3-5 words>\nDESC: <one sentence>"
        )
        prompt = f"Entry: {entry_label} ({entry_path})\nSequence: {chain}\nComponents: {node_count}"
        name = f"{entry_label} Execution Path"
        desc = f"Statically inferred path from {entry_label} through {node_count} components."
        try:
            raw = await self.complete_text(system, [{"role": "user", "content": prompt}], max_tokens=160)
            for line in raw.splitlines():
                if line.startswith("NAME:"):
                    name = line.replace("NAME:", "").strip().strip('"')
                elif line.startswith("DESC:"):
                    desc = line.replace("DESC:", "").strip().strip('"')
        except AIError as err:
            logger.info("Workflow naming falling back to structural text (%s)", err.code)
        return name, desc


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating code fences and surrounding prose."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise AIError("ai_bad_output", "The AI response was not valid JSON. Try again.", 502, True) from None
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            raise AIError("ai_bad_output", "The AI response was not valid JSON. Try again.", 502, True) from None
    if not isinstance(value, dict):
        raise AIError("ai_bad_output", "The AI response was not a JSON object.", 502, True)
    return value


# Global AI client singleton
ai_client = AIClient()
