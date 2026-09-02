"""The set of detectors the decision engine runs. Kept here so callers depend on
the contract, not on individual detector modules."""

from __future__ import annotations

from controlplane_detectors import _models
from controlplane_detectors.base import Detector
from controlplane_detectors.groundedness import GroundednessDetector
from controlplane_detectors.injection import InjectionDetector
from controlplane_detectors.judge import JudgeDetector
from controlplane_detectors.pii import PiiDetector
from controlplane_detectors.toxicity import ToxicityBiasDetector


def default_detectors() -> list[Detector]:
    return [
        PiiDetector(),
        ToxicityBiasDetector(),
        GroundednessDetector(),
        InjectionDetector(),
        JudgeDetector(),
    ]


def warmup() -> None:
    """Load every shared model now (e.g. at service startup) so the first real
    request is not charged for cold model loading, and reported latencies are
    inference-only. Raises if a model cannot be loaded."""
    for load in (
        _models.spacy_nlp,
        _models.presidio_analyzer,
        _models.detoxify_model,
        _models.regard_classifier,
        _models.nli_cross_encoder,
        _models.injection_embedder,
        _models.injection_bank_embeddings,
    ):
        load()
