"""Tests for the conversation ledger."""

import pytest
from controlplane_decision.aggregate import Assessment, CategoryRisk
from controlplane_detectors import Category, Severity
from controlplane_policy import Tier

from controlplane_gateway.config import Settings
from controlplane_gateway.ledger.models import LedgerState
from controlplane_gateway.ledger.scoring import accumulate, score_turn


# Stub config to ensure tests don't rely on environment defaults
@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch):
    monkeypatch.setattr(
        "controlplane_gateway.ledger.scoring.get_settings",
        lambda: Settings(ledger_decay=0.85, ledger_escalation_threshold=1.2),
    )


def test_ledger_escalation_across_turns():
    state = LedgerState(conversation_id="conv1")

    # Turn 1: Medium finding
    risk1 = Assessment(
        risks={
            Category.BIAS: CategoryRisk(
                category=Category.BIAS,
                severity=Severity.MEDIUM,
                confidence=1.0,
                detectors=[],
                spans=[],
            )
        },
        confidence=1.0,
        failed_detectors=[],
    )
    scores1 = score_turn(risk1)
    # Score = 0.55 * 1.0 = 0.55
    state = accumulate(state, scores1, "req1", Tier.ALLOW, 1.0)
    assert state.escalated is False
    assert Category.BIAS in state.residual_risk

    # Turn 2: Same category, Medium finding
    risk2 = Assessment(
        risks={
            Category.BIAS: CategoryRisk(
                category=Category.BIAS,
                severity=Severity.MEDIUM,
                confidence=1.0,
                detectors=[],
                spans=[],
            )
        },
        confidence=1.0,
        failed_detectors=[],
    )
    scores2 = score_turn(risk2)
    # Residual from 1: 0.55 * 0.85 = 0.4675
    # New turn: 0.55
    # Total = 1.0175
    state = accumulate(state, scores2, "req2", Tier.ALLOW, 1.0)
    assert state.escalated is False

    # Turn 3: Same category, Medium finding
    risk3 = Assessment(
        risks={
            Category.BIAS: CategoryRisk(
                category=Category.BIAS,
                severity=Severity.MEDIUM,
                confidence=1.0,
                detectors=[],
                spans=[],
            )
        },
        confidence=1.0,
        failed_detectors=[],
    )
    scores3 = score_turn(risk3)
    # Residual from 2: 1.0175 * 0.85 = 0.864
    # New turn: 0.55
    # Total = 1.414 (> 1.2 threshold)
    state = accumulate(state, scores3, "req3", Tier.ALLOW, 1.0)
    assert state.escalated is True
    assert state.escalated_at_turn == 3


def test_escalated_stays_escalated():
    state = LedgerState(
        conversation_id="conv1", escalated=True, escalated_at_turn=1, escalated_reason="test"
    )

    # Turn 4: Clean
    risk4 = Assessment(risks={}, confidence=1.0, failed_detectors=[])
    scores4 = score_turn(risk4)
    state = accumulate(state, scores4, "req4", Tier.ALLOW, 1.0)

    # Still escalated
    assert state.escalated is True
    assert state.escalated_at_turn == 1
