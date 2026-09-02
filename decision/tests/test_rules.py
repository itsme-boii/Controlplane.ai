from __future__ import annotations

import pytest
from controlplane_detectors import Category, Severity
from controlplane_policy import EffectivePolicy, Tier

from controlplane_decision.aggregate import aggregate
from controlplane_decision.rules import RuleError, evaluate, lint_table
from tests.conftest import failed, result


def _assess(policy, *results):
    return aggregate(list(results), policy)


def test_shipped_tables_all_lint(engine):
    for uc in [None, *engine.usecases]:
        for geo in [None, *engine.jurisdictions]:
            lint_table(engine.resolve(uc, geo))


def test_high_severity_any_category_blocks(base_policy):
    a = _assess(
        base_policy,
        result("d", categories=[Category.TOXICITY], severity=Severity.HIGH, confidence=0.9),
    )
    m = evaluate(a, base_policy)
    assert m.tier is Tier.BLOCK
    assert base_policy.decision_rules[m.index].when == {"category": "any", "min_severity": "high"}


def test_pii_only_finding_routes_to_edit(base_policy):
    a = _assess(
        base_policy,
        result("pii.presidio", categories=[Category.PII], severity=Severity.MEDIUM, confidence=0.8),
    )
    assert evaluate(a, base_policy).tier is Tier.EDIT


def test_pii_alongside_another_finding_does_not_edit(base_policy):
    a = _assess(
        base_policy,
        result("pii.presidio", categories=[Category.PII], severity=Severity.MEDIUM, confidence=0.8),
        result("t", categories=[Category.TOXICITY], severity=Severity.MEDIUM, confidence=0.8),
    )
    # `only: true` fails -> falls through to the generic medium rule
    assert evaluate(a, base_policy).tier is Tier.REVIEW


def test_detector_failure_routes_to_review_before_any_allow(base_policy):
    a = _assess(base_policy, failed("groundedness.nli"))
    m = evaluate(a, base_policy)
    assert m.tier is Tier.REVIEW


def test_groundedness_alias_matches_hallucination_category(base_policy):
    # base rule #3: { category: groundedness, min_severity: medium } -> review
    a = _assess(
        base_policy,
        result(
            "groundedness.nli",
            categories=[Category.HALLUCINATION],
            severity=Severity.MEDIUM,
            confidence=0.7,
        ),
    )
    m = evaluate(a, base_policy)
    assert m.tier is Tier.REVIEW
    assert "groundedness" in base_policy.decision_rules[m.index].when["category"]


def test_clean_falls_through_to_allow(base_policy):
    a = _assess(base_policy, result("pii.presidio", confidence=0.9))
    assert evaluate(a, base_policy).tier is Tier.ALLOW


def test_exhausted_table_defaults_to_review_never_allow():
    policy = EffectivePolicy.model_validate(
        {
            "meta": {"name": "t", "kind": "effective", "effective_from": "2026-01-01"},
            "latency_path": "deep",
            "latency_budget_ms": 1000,
            "confidence_floor": 0.5,
            "checks": {},
            "pii": {"action": "edit"},
            "decision_rules": [
                {"when": {"category": "toxicity", "min_severity": "high"}, "tier": "block"}
            ],
            "retention_days": 30,
        }
    )
    m = evaluate(aggregate([], policy), policy)
    assert m.tier is Tier.REVIEW
    assert m.exhausted is True
    assert m.index is None


def test_only_predicate_needs_a_mixed_check(base_policy):
    pii = result(
        "pii.presidio", categories=[Category.PII], severity=Severity.MEDIUM, confidence=0.8
    )
    tox = result("t", categories=[Category.TOXICITY], severity=Severity.MEDIUM, confidence=0.8)
    rule = {"category": "pii", "only": True, "min_severity": "low"}
    from controlplane_decision.rules import _matches

    assert _matches(rule, aggregate([pii], base_policy)) is True
    assert _matches(rule, aggregate([pii, tox], base_policy)) is False


def test_unknown_predicate_key_is_an_error(base_policy):
    from controlplane_decision.rules import _matches

    with pytest.raises(RuleError):
        _matches({"categoryy": "pii"}, aggregate([], base_policy))


def test_unknown_category_token_is_an_error(base_policy):
    from controlplane_decision.rules import _matches

    with pytest.raises(RuleError):
        _matches({"category": "spookiness", "min_severity": "low"}, aggregate([], base_policy))
