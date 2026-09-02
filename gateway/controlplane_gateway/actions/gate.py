from __future__ import annotations

from controlplane_decision.engine import Decision
from controlplane_policy import EffectivePolicy, Tier
from pydantic import BaseModel

from controlplane_gateway.ledger.models import LedgerState


class ActionDecision(BaseModel):
    tier: Tier
    reason: str


def _rank(tier: Tier) -> int:
    return {Tier.ALLOW: 0, Tier.EDIT: 1, Tier.REVIEW: 2, Tier.BLOCK: 3}[tier]


class ActionGate:
    def evaluate(
        self,
        action_type: str,
        policy: EffectivePolicy,
        text_decision: Decision,
        ledger_state: LedgerState | None,
    ) -> ActionDecision:
        ap = policy.action_policy
        if not ap.enabled:
            return ActionDecision(tier=Tier.ALLOW, reason="action_policy disabled")

        cfg = ap.config_for(action_type)

        if not text_decision.released_text_allowed:
            return ActionDecision(
                tier=Tier.BLOCK,
                reason=(
                    f"originating turn was {text_decision.tier.value}; "
                    "an action never has a higher tier than its own text"
                ),
            )

        if _rank(text_decision.tier) > _rank(cfg.max_text_tier):
            return ActionDecision(
                tier=Tier.REVIEW,
                reason=(
                    f"text tier {text_decision.tier.value} exceeds "
                    f"action policy max {cfg.max_text_tier.value}"
                ),
            )

        if cfg.block_if_ledger_escalated and ledger_state is not None and ledger_state.escalated:
            return ActionDecision(
                tier=Tier.BLOCK,
                reason=f"conversation escalated at turn {ledger_state.escalated_at_turn}",
            )

        if text_decision.confidence < cfg.min_confidence:
            return ActionDecision(
                tier=Tier.REVIEW,
                reason=(
                    f"confidence {text_decision.confidence:.2f} below "
                    f"action floor {cfg.min_confidence:.2f}"
                ),
            )

        return ActionDecision(tier=Tier.ALLOW, reason="within action policy")
