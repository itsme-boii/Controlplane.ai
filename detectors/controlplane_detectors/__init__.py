"""ControlPlane.ai detector library.

Every detector implements the same contract: ``text + context -> DetectionResult``.
The decision engine consumes only ``DetectionResult`` and never imports a concrete
detector, so new detectors register without touching the engine.
"""

from controlplane_detectors.base import (
    Category,
    DetectionResult,
    Detector,
    DetectorContext,
    Severity,
    Span,
)
from controlplane_detectors.groundedness import GroundednessDetector
from controlplane_detectors.pii import PiiDetector
from controlplane_detectors.registry import default_detectors, warmup
from controlplane_detectors.toxicity import ToxicityBiasDetector

__all__ = [
    "Category",
    "DetectionResult",
    "Detector",
    "DetectorContext",
    "GroundednessDetector",
    "PiiDetector",
    "Severity",
    "Span",
    "ToxicityBiasDetector",
    "default_detectors",
    "warmup",
]
