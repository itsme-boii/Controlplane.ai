from __future__ import annotations

from controlplane_detectors import Category, Severity

from controlplane_decision.aggregate import aggregate
from tests.conftest import clean, failed, result


def test_multi_label_finding_contributes_to_every_category(base_policy):
    a = aggregate(
        [
            result(
                "judge",
                categories=[Category.HALLUCINATION, Category.PRIVACY],
                severity=Severity.MEDIUM,
                confidence=0.7,
            )
        ],
        base_policy,
    )
    assert set(a.risks) == {Category.HALLUCINATION, Category.PRIVACY}
    assert a.risks[Category.PRIVACY].severity is Severity.MEDIUM


def test_agreeing_detectors_raise_category_confidence(base_policy):
    a = aggregate(
        [
            result(
                "toxicity_bias.detoxify+regard",
                categories=[Category.BIAS],
                severity=Severity.MEDIUM,
                confidence=0.6,
            ),
            result(
                "judge.groq", categories=[Category.BIAS], severity=Severity.MEDIUM, confidence=0.6
            ),
        ],
        base_policy,
    )
    # noisy-OR of two independent 0.6 signals > either alone
    assert a.risks[Category.BIAS].confidence > 0.6
    assert a.risks[Category.BIAS].detectors == [
        "toxicity_bias.detoxify+regard",
        "judge.groq",
    ]


def test_worst_severity_wins_per_category(base_policy):
    a = aggregate(
        [
            result("d1", categories=[Category.TOXICITY], severity=Severity.LOW, confidence=0.3),
            result("d2", categories=[Category.TOXICITY], severity=Severity.HIGH, confidence=0.9),
        ],
        base_policy,
    )
    assert a.risks[Category.TOXICITY].severity is Severity.HIGH
    assert a.max_severity is Severity.HIGH


def test_failed_detector_is_recorded_not_treated_as_clean(base_policy):
    a = aggregate([clean("pii.presidio"), failed("groundedness.nli", "nli down")], base_policy)
    assert a.failed_detectors == ["groundedness.nli"]
    assert a.risks == {}
    # the clean detector's confidence still informs the "clean" verdict
    assert a.confidence == 0.9


def test_abstention_is_distinct_from_a_clean_pass(base_policy):
    a = aggregate(
        [
            clean("pii.presidio", confidence=0.8),
            result("groundedness.nli", evidence={"assessable": False}),
        ],
        base_policy,
    )
    assert a.unassessable_checks == ["groundedness"]
    assert a.failed_detectors == []
    # abstention does not drag confidence down; the clean signal stands
    assert a.confidence == 0.8


def test_clean_confidence_is_the_least_sure_detector(base_policy):
    a = aggregate(
        [clean("pii.presidio", 0.9), clean("toxicity_bias.detoxify+regard", 0.55)], base_policy
    )
    assert a.confidence == 0.55
