from __future__ import annotations

from controlplane_detectors import Category, Severity, Span
from controlplane_policy import Tier

from controlplane_decision import DecisionEngine
from tests.conftest import clean, result

E = DecisionEngine()


def test_clean_response_is_allowed(base_policy):
    d = E.decide(
        "The build passes.",
        [clean("pii.presidio"), clean("toxicity_bias.detoxify+regard")],
        base_policy,
    )
    assert d.tier is Tier.ALLOW
    assert d.fail_safe_triggered is False
    assert d.released_text_allowed is True


def test_pii_only_response_is_edited_and_redaction_attached(base_policy):
    text = "Reach me at jane@acme.com."
    start = text.index("jane@acme.com")
    span = Span(
        start=start, end=start + len("jane@acme.com"), text="jane@acme.com", label="EMAIL_ADDRESS"
    )
    pii = result(
        "pii.presidio",
        categories=[Category.PII],
        severity=Severity.MEDIUM,
        confidence=0.85,
        spans=[span],
    )
    d = E.decide(text, [pii], base_policy)
    assert d.tier is Tier.EDIT
    assert d.redaction is not None
    assert "jane@acme.com" not in d.redaction.text
    assert d.released_text_allowed is True


def test_high_severity_blocks_and_withholds_text(base_policy):
    d = E.decide(
        "slur-laden text",
        [
            result(
                "toxicity_bias.detoxify+regard",
                categories=[Category.TOXICITY],
                severity=Severity.HIGH,
                confidence=0.97,
            )
        ],
        base_policy,
    )
    assert d.tier is Tier.BLOCK
    assert d.released_text_allowed is False


def test_medium_finding_goes_to_review(base_policy):
    d = E.decide(
        "borderline",
        [
            result(
                "toxicity_bias.detoxify+regard",
                categories=[Category.TOXICITY],
                severity=Severity.MEDIUM,
                confidence=0.7,
            )
        ],
        base_policy,
    )
    assert d.tier is Tier.REVIEW


def test_pii_only_high_sensitivity_is_masked_not_blocked(base_policy):
    text = "Her SSN is 219-09-9999."
    start = text.index("219-09-9999")
    d = E.decide(
        text,
        [
            result(
                "pii.presidio",
                categories=[Category.PII],
                severity=Severity.HIGH,
                confidence=0.9,
                spans=[Span(start=start, end=start + 11, text="219-09-9999", label="US_SSN")],
            )
        ],
        base_policy,
    )
    assert Category.PII in d.assessment.risks
    assert d.tier is Tier.EDIT  # PII is the only finding -> mask and ship
    assert "219-09-9999" not in d.redaction.text
    assert d.rationale.startswith("edit:")
    assert d.confidence == 0.9


def test_stricter_jurisdiction_changes_the_outcome(engine):
    # decisionsupport blocks medium bias outright; base only reviews it.
    ds = engine.resolve("decisionsupport", None)
    bias = result(
        "toxicity_bias.detoxify+regard",
        categories=[Category.BIAS],
        severity=Severity.MEDIUM,
        confidence=0.8,
    )
    assert E.decide("x", [bias], ds).tier is Tier.BLOCK
    assert E.decide("x", [bias], engine.resolve(None, None)).tier is Tier.REVIEW
