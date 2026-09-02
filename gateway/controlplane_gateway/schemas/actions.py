from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ActionRequest(BaseModel):
    request_id: str
    conversation_id: str | None = None
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ActionResponse(BaseModel):
    action_id: str
    action_decision: str
    executed: bool
    result: dict[str, Any] | None = None
    reason: str
