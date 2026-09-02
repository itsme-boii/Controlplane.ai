"""Provider interface. One method: forward a chat completion, return the parsed response."""

from __future__ import annotations

import abc

from controlplane_gateway.schemas.openai import ChatCompletionRequest, ChatCompletionResponse


class ProviderError(RuntimeError):
    """Raised when the upstream model call fails or is misconfigured.

    The gateway never swallows this into a fake success — it surfaces as a 502
    and (later phases) an escalation.
    """


class ModelProvider(abc.ABC):
    name: str
    default_model: str

    @abc.abstractmethod
    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse: ...

    @abc.abstractmethod
    async def aclose(self) -> None: ...
