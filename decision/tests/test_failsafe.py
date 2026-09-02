"""The no-false-fallback exit gate (docs/discussion.md Phase 4).

Every path where evidence is missing, incomplete, or low-confidence must land on
`review` (or stricter) — never `allow`, never `edit`. These assertions are the
concrete test for the governing rule and are a required gate, not advisory.
"""

from __future__ import annotations

import pytest
from controlplane_detectors import Category, DetectionResult, Severity, Span
from controlplane_policy import EffectivePolicy, Tier

from controlplane_decision import DecisionEngine
from tests.conftest import clean, failed, result

E = DecisionEngine()


def _policy(**over) -> EffectivePolicy:
    spec = {
        "meta": {"name": "t", "kind": "effective", "effective_from": "2026-01-01"},
        "latency_path": "deep",
        "latency_budget_ms": 1000,
        "confidence_floor": 0.5,
        "checks": {},
        "pii": {"action": "edit", "entities": []},
        "decision_rules": [{"when": {"always": True}, "tier": "allow"}],
        "retention_days": 30,
    }
    spec.update(over)
    return EffectivePolicy.model_validate(spec)


def test_failed_detector_never_allows_even_if_the_table_would(base_policy):
    # A permissive table that only has `always -> allow`.
    permissive = _policy()
    d = E.decide("x", [clean("pii.presidio"), failed("groundedness.nli", "timeout")], permissive)
    assert d.tier is Tier.REVIEW
    assert d.fail_safe_triggered is True
    assert "never allows" in d.rationale


def test_failed_detector_downgrades_an_edit_to_review():
    table = _policy(
        decision_rules=[
            {"when": {"category": "pii", "min_severity": "low"}, "tier": "edit"},
            {"when": {"always": True}, "tier": "allow"},
        ]
    )
    pii = result(
        "pii.presidio",
        categories=[Category.PII],
        severity=Severity.MEDIUM,
        confidence=0.9,
        spans=[Span(start=0, end=1, text="x", label="EMAIL_ADDRESS")],
    )
    d = E.decide("x", [pii, failed("toxicity_bias.detoxify+regard")], table)
    assert d.tier is Tier.REVIEW
    assert d.fail_safe_triggered is True


def test_timed_out_detector_mid_check_routes_to_review(base_policy):
    # Simulates the required test: kill a detector mid-check.
    timed_out = DetectionResult.failed("toxicity_bias.detoxify+regard", "asyncio.TimeoutError")
    d = E.decide("looks fine", [clean("pii.presidio"), timed_out], base_policy)
    assert d.tier is Tier.REVIEW
    assert d.assessment.failed_detectors == ["toxicity_bias.detoxify+regard"]


def test_low_confidence_clean_result_abstains_to_review(base_policy):
    d = E.decide("x", [clean("pii.presidio", confidence=0.30)], base_policy)
    assert d.tier is Tier.REVIEW


def test_confidence_floor_clamp_fires_even_without_an_explicit_rule():
    table = _policy(confidence_floor=0.8)  # only rule is always -> allow
    d = E.decide("x", [clean("pii.presidio", confidence=0.6)], table)
    assert d.tier is Tier.REVIEW
    assert d.fail_safe_triggered is True
    assert "below policy floor" in d.rationale


def test_exhausted_table_is_review_not_allow():
    table = _policy(
        decision_rules=[{"when": {"category": "toxicity", "min_severity": "high"}, "tier": "block"}]
    )
    d = E.decide("x", [clean("pii.presidio")], table)
    assert d.tier is Tier.REVIEW
    assert d.fail_safe_triggered is True


def test_edit_with_no_maskable_span_becomes_review():
    table = _policy(
        decision_rules=[
            {"when": {"category": "pii", "min_severity": "low"}, "tier": "edit"},
            {"when": {"always": True}, "tier": "allow"},
        ]
    )
    # PII flagged but the detector supplied no spans -> nothing to mask.
    pii = result(
        "pii.presidio", categories=[Category.PII], severity=Severity.MEDIUM, confidence=0.9
    )
    d = E.decide("some text", [pii], table)
    assert d.tier is Tier.REVIEW
    assert d.redaction is None
    assert d.fail_safe_triggered is True


def test_all_out_of_scope_spans_means_the_edit_cannot_be_performed():
    table = _policy(
        pii={"action": "edit", "entities": ["US_SSN"]},
        decision_rules=[
            {"when": {"category": "pii", "min_severity": "low"}, "tier": "edit"},
            {"when": {"always": True}, "tier": "allow"},
        ],
    )
    text = "Contact jane@acme.com."
    span = Span(
        start=text.index("jane@acme.com"),
        end=text.index("jane@acme.com") + 13,
        text="jane@acme.com",
        label="EMAIL_ADDRESS",
    )
    pii = result(
        "pii.presidio",
        categories=[Category.PII],
        severity=Severity.MEDIUM,
        confidence=0.9,
        spans=[span],
    )
    d = E.decide(text, [pii], table)
    # policy only permits masking US_SSN, so the email stays -> we will not ship it as "edited"
    assert d.tier is Tier.REVIEW
    assert d.fail_safe_triggered is True


def test_a_genuinely_clean_high_confidence_result_still_allows(base_policy):
    # The gate must not be so blunt it escalates everything.
    d = E.decide(
        "The deploy finished at noon.",
        [clean("pii.presidio", 0.95), clean("toxicity_bias.detoxify+regard", 0.9)],
        base_policy,
    )
    assert d.tier is Tier.ALLOW
    assert d.fail_safe_triggered is False


@pytest.mark.parametrize("geo", [None, "us", "eu"])
def test_failure_escalates_under_every_jurisdiction(engine, geo):
    policy = engine.resolve("knowledgecopilot", geo)
    d = E.decide("x", [failed("pii.presidio")], policy)
    assert d.tier in (Tier.REVIEW, Tier.BLOCK)
