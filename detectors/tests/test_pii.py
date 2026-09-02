import pytest

from controlplane_detectors import pii
from controlplane_detectors.base import Category, Severity
from controlplane_detectors.pii import PiiDetector

pytestmark = pytest.mark.models


async def test_flags_high_sensitivity_identifiers(ctx):
    text = "Contact John Doe at john.doe@example.com; his SSN is 219-09-9999."
    result = await PiiDetector().analyze(text, ctx)

    assert result.ok
    assert Category.PII in result.categories
    assert Category.PRIVACY in result.categories  # SSN present
    assert result.severity is Severity.HIGH
    labels = {s.label for s in result.spans}
    assert "US_SSN" in labels and "EMAIL_ADDRESS" in labels
    assert result.evidence["entities"].get("US_SSN") == 1


async def test_clean_text_is_a_confident_negative(ctx):
    result = await PiiDetector().analyze("The build pipeline runs unit tests before deploy.", ctx)

    assert result.ok
    assert result.severity is Severity.NONE
    assert result.spans == []
    assert result.confidence > 0.5


async def test_detector_failure_is_not_a_clean_pass(ctx, monkeypatch):
    def boom():
        raise RuntimeError("presidio down")

    monkeypatch.setattr(pii, "presidio_analyzer", boom)
    result = await PiiDetector().analyze("john.doe@example.com", ctx)

    assert result.ok is False
    assert result.severity is Severity.NONE
    assert "presidio" in result.rationale
