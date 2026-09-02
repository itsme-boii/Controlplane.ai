from controlplane_detectors import Category, DetectionResult, Severity


def test_default_result_is_clean():
    r = DetectionResult(detector="x")
    assert r.ok is True
    assert r.categories == []
    assert r.severity is Severity.NONE
    assert r.confidence == 0.0


def test_failed_result_flags_missing_evidence():
    r = DetectionResult.failed("pii", "presidio unavailable")
    assert r.ok is False
    assert r.confidence == 0.0
    assert "presidio" in r.rationale


def test_multi_label_categories():
    r = DetectionResult(
        detector="judge",
        categories=[Category.HALLUCINATION, Category.PRIVACY],
        severity=Severity.MEDIUM,
        confidence=0.6,
    )
    assert Category.HALLUCINATION in r.categories
    assert Category.PRIVACY in r.categories
