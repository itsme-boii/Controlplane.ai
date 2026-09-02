"""Fixtures for the decision-engine suite. Detector results are constructed
directly — the engine is pure and needs no models."""

from __future__ import annotations

from pathlib import Path

import pytest
from controlplane_detectors import Category, DetectionResult, Severity, Span
from controlplane_policy import EffectivePolicy, PolicyEngine, PolicyRepo

_POLICIES_DIR = Path(__file__).resolve().parents[2] / "policies"


@pytest.fixture(scope="session")
def engine() -> PolicyEngine:
    return PolicyEngine(PolicyRepo.from_dir(_POLICIES_DIR))


@pytest.fixture
def base_policy(engine: PolicyEngine) -> EffectivePolicy:
    return engine.resolve(None, None)


def result(
    detector: str,
    *,
    ok: bool = True,
    categories: list[Category] | None = None,
    severity: Severity = Severity.NONE,
    confidence: float = 0.0,
    spans: list[Span] | None = None,
    evidence: dict | None = None,
) -> DetectionResult:
    return DetectionResult(
        detector=detector,
        ok=ok,
        categories=categories or [],
        severity=severity,
        confidence=confidence,
        spans=spans or [],
        evidence=evidence or {},
    )


def clean(detector: str, confidence: float = 0.9) -> DetectionResult:
    return result(detector, confidence=confidence)


def failed(detector: str, reason: str = "unavailable") -> DetectionResult:
    return DetectionResult.failed(detector, reason)
