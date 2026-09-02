"""Aggregate raw detector outputs into a per-category risk picture.

Detector results are multi-label: one finding can carry several categories (a
fabricated fact about a real person is HALLUCINATION + PRIVACY). The aggregator
collapses the list of :class:`DetectionResult` into:

* one :class:`CategoryRisk` per category any detector raised, with the worst
  severity seen and a confidence that reflects detector *agreement*;
* the list of detectors that could not complete (``ok is False``) — carried
  through untouched so the decision engine can enforce the no-false-fallback
  rule;
* the list of enabled checks that ran but could not assess anything
  (e.g. groundedness with no source documents) — an honest "don't know", kept
  distinct from both a clean pass and a failure.
"""

from __future__ import annotations

from controlplane_detectors import Category, DetectionResult, Severity, Span
from controlplane_policy import EffectivePolicy
from pydantic import BaseModel, Field

from controlplane_decision.severity import RANK, worst


class CategoryRisk(BaseModel):
    category: Category
    severity: Severity
    confidence: float
    detectors: list[str]
    spans: list[Span] = Field(default_factory=list)


class Assessment(BaseModel):
    """The evidence the decision table is evaluated against."""

    risks: dict[Category, CategoryRisk] = Field(default_factory=dict)
    failed_detectors: list[str] = Field(default_factory=list)
    unassessable_checks: list[str] = Field(default_factory=list)
    # Confidence in the finding that will drive the decision (or, when nothing
    # was found, in the "clean" verdict itself). See `_overall_confidence`.
    confidence: float = 0.0

    @property
    def max_severity(self) -> Severity:
        return worst(*(r.severity for r in self.risks.values()))

    @property
    def categories(self) -> set[Category]:
        return {c for c, r in self.risks.items() if r.severity is not Severity.NONE}

    def has_only(self, category: Category) -> bool:
        return self.categories == {category}


def _combine_confidence(values: list[float]) -> float:
    """Independent detectors that agree raise confidence (noisy-OR); a lone
    detector contributes its own number."""
    if len(values) == 1:
        return round(values[0], 3)
    agreement = 1.0
    for v in values:
        agreement *= 1.0 - v
    return round(min(0.99, 1.0 - agreement), 3)


def _overall_confidence(risks: dict[Category, CategoryRisk], clean_signals: list[float]) -> float:
    flagged = [r for r in risks.values() if r.severity is not Severity.NONE]
    if flagged:
        top = max(RANK[r.severity] for r in flagged)
        # Confidence in the most severe finding — that is what a rule will fire on.
        return round(max(r.confidence for r in flagged if RANK[r.severity] == top), 3)
    if clean_signals:
        # No findings: only as sure as the least-sure detector that looked.
        return round(min(clean_signals), 3)
    return 0.0


def _disabled(policy: EffectivePolicy) -> set[str]:
    return {name for name, cfg in policy.checks.items() if not cfg.enabled}


def aggregate(results: list[DetectionResult], policy: EffectivePolicy) -> Assessment:
    by_category: dict[Category, dict[str, list]] = {}
    failed: list[str] = []
    unassessable: list[str] = []
    clean_signals: list[float] = []
    disabled = _disabled(policy)

    for res in results:
        # Detector names are "<check>.<impl>" by convention (pii.presidio, …). A
        # result for a check this policy switched off is not part of its
        # assessment at all — neither risk nor evidence of safety.
        if res.detector.split(".", 1)[0] in disabled:
            continue

        if not res.ok:
            failed.append(res.detector)
            continue

        if not res.categories or res.severity is Severity.NONE:
            # A real "nothing here" — but only evidence of absence if the
            # detector actually assessed something.
            if res.evidence.get("assessable") is False:
                unassessable.append(res.detector.split(".", 1)[0])
            else:
                clean_signals.append(res.confidence or 0.0)
            continue

        for category in res.categories:
            slot = by_category.setdefault(category, {"sev": [], "conf": [], "det": [], "spans": []})
            slot["sev"].append(res.severity)
            slot["conf"].append(res.confidence)
            slot["det"].append(res.detector)
            slot["spans"].extend(res.spans)

    risks = {
        category: CategoryRisk(
            category=category,
            severity=worst(*slot["sev"]),
            confidence=_combine_confidence(slot["conf"]),
            detectors=slot["det"],
            spans=slot["spans"],
        )
        for category, slot in by_category.items()
    }

    assessment = Assessment(
        risks=risks,
        failed_detectors=failed,
        unassessable_checks=sorted(set(unassessable)),
    )
    assessment.confidence = _overall_confidence(risks, clean_signals)
    return assessment
