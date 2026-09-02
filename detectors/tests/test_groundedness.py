import pytest

from controlplane_detectors import groundedness
from controlplane_detectors.base import Category, DetectorContext, Severity
from controlplane_detectors.groundedness import GroundednessDetector

pytestmark = pytest.mark.models

_SOURCE = (
    "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, "
    "France. It was completed in 1889 and stands 330 metres tall."
)


async def test_contradicted_claim_is_a_hallucination():
    ctx = DetectorContext(source_documents=[_SOURCE])
    result = await GroundednessDetector().analyze("The Eiffel Tower is in Berlin.", ctx)

    assert result.ok
    assert Category.HALLUCINATION in result.categories
    assert result.severity is Severity.HIGH
    assert result.evidence["contradicted"] == 1
    assert any(s.label == "contradicted" for s in result.spans)


async def test_entailed_claim_is_grounded():
    ctx = DetectorContext(source_documents=[_SOURCE])
    result = await GroundednessDetector().analyze(
        "The Eiffel Tower was completed in 1889 and is located in Paris.", ctx
    )
    assert result.ok
    assert result.severity is Severity.NONE
    assert result.evidence["contradicted"] == 0


async def test_no_sources_means_abstain_not_guess():
    result = await GroundednessDetector().analyze("The sky is green.", DetectorContext())

    assert result.ok is True
    assert result.evidence["assessable"] is False
    assert result.confidence == 0.0
    assert result.severity is Severity.NONE


async def test_model_failure_is_not_a_clean_pass(monkeypatch):
    def boom():
        raise RuntimeError("nli down")

    monkeypatch.setattr(groundedness, "nli_cross_encoder", boom)
    ctx = DetectorContext(source_documents=[_SOURCE])
    result = await GroundednessDetector().analyze("The Eiffel Tower is in Paris.", ctx)

    assert result.ok is False
    assert "nli" in result.rationale
