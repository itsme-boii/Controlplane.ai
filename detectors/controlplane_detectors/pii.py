"""PII / privacy detector — Microsoft Presidio (spaCy NER + regex + checksum validators)."""

from __future__ import annotations

import asyncio
import time

from controlplane_detectors._models import presidio_analyzer
from controlplane_detectors.base import (
    Category,
    DetectionResult,
    Detector,
    DetectorContext,
    Severity,
    Span,
)

# Identifiers that single someone out directly / carry regulatory weight.
_HIGH_SENSITIVITY = {
    "US_SSN",
    "US_ITIN",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
    "US_BANK_NUMBER",
    "CREDIT_CARD",
    "CRYPTO",
    "IBAN_CODE",
    "MEDICAL_LICENSE",
}
# Contextual / quasi-identifiers — meaningful in aggregate, lower on their own.
_LOW_SENSITIVITY = {"DATE_TIME", "NRP", "LOCATION", "URL"}

_SCORE_THRESHOLD = 0.5


class PiiDetector(Detector):
    name = "pii.presidio"
    check = "pii"

    async def analyze(self, text: str, context: DetectorContext) -> DetectionResult:
        started = time.perf_counter()
        try:
            analyzer = presidio_analyzer()
            findings = await asyncio.to_thread(
                analyzer.analyze,
                text=text,
                language="en",
                score_threshold=_SCORE_THRESHOLD,
            )
        except Exception as exc:  # model/dependency failure -> missing evidence, not "clean"
            return DetectionResult.failed(self.name, f"presidio unavailable: {exc}")

        latency_ms = (time.perf_counter() - started) * 1000
        if not findings:
            return DetectionResult(
                detector=self.name,
                severity=Severity.NONE,
                confidence=0.9,  # a clean Presidio pass is itself decent evidence of absence
                rationale="no PII entities detected",
                latency_ms=latency_ms,
            )

        spans = [
            Span(start=f.start, end=f.end, text=text[f.start : f.end], label=f.entity_type)
            for f in findings
        ]
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.entity_type] = counts.get(f.entity_type, 0) + 1
        max_score = max(f.score for f in findings)
        has_high = any(f.entity_type in _HIGH_SENSITIVITY for f in findings)
        only_low = all(f.entity_type in _LOW_SENSITIVITY for f in findings)

        if has_high:
            severity = Severity.HIGH
        elif only_low:
            severity = Severity.LOW
        else:
            severity = Severity.MEDIUM

        categories = [Category.PII]
        if has_high:
            categories.append(Category.PRIVACY)

        return DetectionResult(
            detector=self.name,
            categories=categories,
            severity=severity,
            confidence=round(float(max_score), 3),
            spans=spans,
            evidence={"entities": counts, "max_score": round(float(max_score), 3)},
            rationale=f"detected {sum(counts.values())} PII span(s): "
            + ", ".join(f"{k}×{v}" for k, v in sorted(counts.items())),
            latency_ms=latency_ms,
        )
