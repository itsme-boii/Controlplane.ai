"""Groq backend. Groq exposes an OpenAI-compatible REST API, so this is a thin
authenticated pass-through with typed parsing and explicit error surfacing."""

from __future__ import annotations

import httpx

from controlplane_gateway.config import Settings
from controlplane_gateway.models.base import ModelProvider, ProviderError
from controlplane_gateway.schemas.openai import ChatCompletionRequest, ChatCompletionResponse


class GroqProvider(ModelProvider):
    name = "groq"

    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise ProviderError("GROQ_API_KEY is not set")
        self.default_model = settings.groq_model
        self._client = httpx.AsyncClient(
            base_url=settings.groq_base_url,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=settings.model_timeout_s,
        )

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload: dict = {
            "model": request.model or self.default_model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "stream": False,
            **request.extra_params(),
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        try:
            resp = await self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:  # network/timeout — real failure, not a safe default
            raise ProviderError(f"groq request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise ProviderError(f"groq returned {resp.status_code}: {resp.text[:500]}")

        try:
            return ChatCompletionResponse.model_validate(resp.json())
        except ValueError as exc:
            raise ProviderError(f"groq returned an unparseable body: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()
