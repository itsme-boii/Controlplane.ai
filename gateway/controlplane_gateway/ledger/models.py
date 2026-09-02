"""Models for the conversation risk ledger."""

from __future__ import annotations

from datetime import datetime

from controlplane_detectors import Category, Severity
from controlplane_policy import Tier
from pydantic import BaseModel, Field


class LedgerTurn(BaseModel):
    request_id: str
    turn_index: int
    created_at: datetime
    categories: dict[Category, Severity]
    tier: Tier
    confidence: float


class LedgerState(BaseModel):
    conversation_id: str
    turns: list[LedgerTurn] = Field(default_factory=list)
    residual_risk: dict[Category, float] = Field(default_factory=dict)
    escalated: bool = False
    escalated_at_turn: int | None = None
    escalated_reason: str = ""
