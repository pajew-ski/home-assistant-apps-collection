"""Async Ollama client for LLM inference."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OllamaClient:
    """Thin async wrapper around Ollama's ``/api/chat`` endpoint."""

    def __init__(
        self,
        base_url: str = "http://host.docker.internal:11434",
        model: str = "llama3.2",
        max_tokens: int = 4096,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Send a chat completion request.  Returns the assistant message content."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": self.max_tokens,
            },
        }
        if system:
            payload["messages"] = [{"role": "system", "content": system}, *messages]
        if tools:
            payload["tools"] = tools

        try:
            resp = await self.client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP error %s: %s", exc.response.status_code, exc.response.text[:300])
            return ""
        except Exception as exc:
            logger.error("Ollama request failed: %s", exc)
            return ""

    async def health_check(self) -> bool:
        """Check if Ollama is reachable and the model is available."""
        try:
            resp = await self.client.get("/api/tags")
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            # Accept both exact match and match without tag suffix
            return any(self.model in m for m in models)
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
