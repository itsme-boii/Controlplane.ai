"""Scoring logic for the conversation risk ledger."""

from __future__ import annotations

from datetime import UTC, datetime

from controlplane_decision.aggregate import Assessment
from controlplane_detectors import Category, Severity
from controlplane_policy import Tier

from controlplane_gateway.config import get_settings
from controlplane_gateway.ledger.models import LedgerState, LedgerTurn

_SEVERITY_SCORE = {
    Severity.NONE: 0.0,
    Severity.LOW: 0.25,
    Severity.MEDIUM: 0.55,
    Severity.HIGH: 0.9,
}


def score_turn(assessment: Assessment) -> dict[Category, tuple[Severity, float]]:
    """(severity, severity * confidence) per category present in this turn."""
    scores: dict[Category, tuple[Severity, float]] = {}
    for cat, risk in assessment.risks.items():
        if risk.severity != Severity.NONE:
            scores[cat] = (risk.severity, _SEVERITY_SCORE[risk.severity] * assessment.confidence)
    return scores


def accumulate(
    state: LedgerState,
    turn_scores: dict[Category, tuple[Severity, float]],
    request_id: str,
    tier: Tier,
    confidence: float,
) -> LedgerState:
    """Decay existing residual_risk, add this turn's scores, check the threshold."""
    settings = get_settings()
    decay = settings.ledger_decay
    threshold = settings.ledger_escalation_threshold

    turn_index = len(state.turns) + 1

    # 1. Decay existing risk
    new_residual: dict[Category, float] = {}
    for cat, risk in state.residual_risk.items():
        decayed = risk * decay
        if decayed > 0.01:  # Drop negligible risk
            new_residual[cat] = decayed

    # 2. Add new turn risk
    categories_present: dict[Category, Severity] = {}
    for cat, (severity, score) in turn_scores.items():
        new_residual[cat] = new_residual.get(cat, 0.0) + score
        categories_present[cat] = severity

    turn = LedgerTurn(
        request_id=request_id,
        turn_index=turn_index,
        created_at=datetime.now(UTC),
        categories=categories_present,
        tier=tier,
        confidence=confidence,
    )

    # 3. Check for escalation
    escalated = state.escalated
    escalated_at_turn = state.escalated_at_turn
    escalated_reason = state.escalated_reason

    if not escalated:
        for cat, risk in new_residual.items():
            if risk >= threshold:
                escalated = True
                escalated_at_turn = turn_index
                escalated_reason = (
                    f"residual risk for {cat.value} ({risk:.2f}) crossed threshold ({threshold})"
                )
                break

    return LedgerState(
        conversation_id=state.conversation_id,
        turns=state.turns + [turn],
        residual_risk=new_residual,
        escalated=escalated,
        escalated_at_turn=escalated_at_turn,
        escalated_reason=escalated_reason,
    )
