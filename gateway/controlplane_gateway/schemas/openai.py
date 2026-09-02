"""Minimal OpenAI-compatible chat-completions schema.

Only the fields the gateway needs are typed; unknown fields are preserved and
forwarded verbatim so callers relying on provider-specific params still work.
Streaming is intentionally out of scope for Phase 1.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None

    def drop_reasoning(self) -> None:
        """Remove provider chain-of-thought fields. The gateway inspects and
        redacts ``content``; it does not (yet) govern the raw reasoning trace, so
        it must not forward it — that would be an ungoverned output channel."""
        for key in ("reasoning", "reasoning_content"):
            if self.__pydantic_extra__ is not None:
                self.__pydantic_extra__.pop(key, None)


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str | None = None
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    # ControlPlane extension: the grounding documents the answer must be
    # consistent with (RAG context). Consumed by the groundedness check and
    # stripped before the request is forwarded upstream.
    source_documents: list[str] | None = None

    def extra_params(self) -> dict[str, Any]:
        """Provider-passthrough params the gateway does not interpret itself."""
        known = {
            "model",
            "messages",
            "temperature",
            "max_tokens",
            "stream",
            "source_documents",
        }
        return {k: v for k, v in self.model_dump().items() if k not in known and v is not None}

    def last_user_text(self) -> str:
        for message in reversed(self.messages):
            if message.role == "user" and isinstance(message.content, str):
                return message.content
        return ""


class Usage(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatChoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int = 0
    message: ChatMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: Usage = Field(default_factory=Usage)

    def drop_reasoning(self) -> None:
        for choice in self.choices:
            choice.message.drop_reasoning()

    def first_text(self) -> str:
        if not self.choices:
            return ""
        content = self.choices[0].message.content
        return content if isinstance(content, str) else ""
