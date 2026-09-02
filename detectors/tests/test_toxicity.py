import pytest

from controlplane_detectors import toxicity
from controlplane_detectors.base import Category, Severity
from controlplane_detectors.toxicity import ToxicityBiasDetector, _swap_terms

pytestmark = pytest.mark.models


def test_swap_terms_is_bidirectional_and_case_preserving():
    assert _swap_terms("He is a Man", [("he", "she"), ("man", "woman")]) == "She is a Woman"
    assert _swap_terms("she", [("he", "she")]) == "he"


async def test_overt_toxicity_is_flagged(ctx):
    result = await ToxicityBiasDetector().analyze(
        "You are a disgusting idiot and everyone hates you.", ctx
    )

    assert result.ok
    assert Category.TOXICITY in result.categories
    assert result.severity in (Severity.MEDIUM, Severity.HIGH)
    assert result.evidence["detoxify"]["toxicity"] > 0.5


async def test_neutral_text_is_clean(ctx):
    result = await ToxicityBiasDetector().analyze(
        "The train departs at nine and arrives by noon.", ctx
    )
    assert result.ok
    assert result.severity is Severity.NONE


async def test_primary_signal_failure_fails_the_detector(ctx, monkeypatch):
    class Boom:
        def predict(self, _text):
            raise RuntimeError("detoxify down")

    monkeypatch.setattr(toxicity, "detoxify_model", lambda: Boom())
    result = await ToxicityBiasDetector().analyze("hello", ctx)
    assert result.ok is False


async def test_regard_failure_degrades_honestly(ctx, monkeypatch):
    def boom():
        raise RuntimeError("regard down")

    monkeypatch.setattr(toxicity, "regard_classifier", boom)
    result = await ToxicityBiasDetector().analyze("You are an idiot.", ctx)

    assert result.ok is True  # primary signal still ran
    assert result.evidence["regard_available"] is False
    assert "unavailable" in result.rationale
    assert result.confidence <= 0.6
