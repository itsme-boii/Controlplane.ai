"""Policy schema.

A *pack* is one YAML file. Packs come in three kinds:

- ``base``          — the default policy, fully specified.
- ``usecase``       — per-application overrides (SupportAssist, KnowledgeCopilot, …).
- ``jurisdiction``  — geo overlay (US baseline, EU stricter).

Resolution deep-merges ``base <- usecase <- jurisdiction`` (later layers win) and
validates the result against :class:`EffectivePolicy` — the single strict schema
the rest of the system consumes.
"""

from __future__ import annotations

import datetime as dt
import enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Tier(enum.StrEnum):
    ALLOW = "allow"
    EDIT = "edit"
    REVIEW = "review"
    BLOCK = "block"


class LatencyPath(enum.StrEnum):
    # fast: cheap deterministic checks inline, LLM-judge runs post-hoc.
    # deep: every check inline, response held until the verdict.
    FAST = "fast"
    DEEP = "deep"


class Severity(enum.StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CheckConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    # On the deep path a blocking check holds the response until it returns; on
    # the fast path a non-blocking check still runs but cannot delay the reply.
    blocking: bool = True
    # Detector score at/above which a finding is raised, and the severity it maps
    # to. Keys are detector-specific (e.g. "toxicity", "identity_attack").
    thresholds: dict[str, float] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)


class PiiHandling(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Tier = Tier.EDIT  # what to do when PII is the *only* finding
    entities: list[str] = Field(default_factory=list)
    mask_char: str = "•"


class DecisionRule(BaseModel):
    """One row of the deterministic decision table. Rules are evaluated in order;
    the first whose ``when`` matches decides the tier. Evaluation itself lands in
    Phase 4 — Phase 2 only carries and merges the rules as data."""

    model_config = ConfigDict(extra="forbid")

    when: dict[str, Any]
    tier: Tier
    note: str = ""


class PolicyMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # "effective" is the synthesized kind of a merged/resolved policy.
    kind: Literal["base", "usecase", "jurisdiction", "effective"]
    description: str = ""
    effective_from: dt.date


class ActionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_confidence: float = Field(ge=0.0, le=1.0)
    # The accompanying text decision must be at least this tier for the action to be
    # even considered; a text `review`/`block` always blocks the action too, regardless
    # of this config (enforced in code, not data — see ActionGate below).
    max_text_tier: Tier = Tier.ALLOW
    block_if_ledger_escalated: bool = True

class ActionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    actions: dict[str, ActionConfig] = Field(default_factory=dict)

    def config_for(self, action_type: str) -> ActionConfig:
        return self.actions.get(action_type) or self.actions.get(
            "default", ActionConfig(min_confidence=0.85)
        )


class EffectivePolicy(BaseModel):
    """The merged, resolved policy for one (use-case, jurisdiction) pair."""

    model_config = ConfigDict(extra="forbid")

    meta: PolicyMeta
    latency_path: LatencyPath
    latency_budget_ms: int
    confidence_floor: float = Field(ge=0.0, le=1.0)
    checks: dict[str, CheckConfig]
    pii: PiiHandling
    decision_rules: list[DecisionRule]
    retention_days: int
    action_policy: ActionPolicy = Field(default_factory=ActionPolicy)

    # Populated by the resolver; not written in YAML.
    version: str = ""
    resolved_from: list[str] = Field(default_factory=list)

    def enabled_checks(self) -> list[str]:
        return [name for name, cfg in self.checks.items() if cfg.enabled]
