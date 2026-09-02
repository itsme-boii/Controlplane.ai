"""Toxicity & bias detector — two independent free signals.

* **Detoxify** ('unbiased-small') — direct toxicity probabilities. Primary
  signal: if it cannot run, the whole detector fails (ok=False -> review).
* **regardv3** — the classifier behind the HF ``regard`` fairness metric, used
  two ways: a direct negative-regard read on the text, and a *demographic-swap
  differential* (swap group-referential terms, re-score, measure the gap).
  Confirmatory signal: if it cannot run we still return a result but cap
  confidence and say so (honest degradation, not a silent pass).
"""

from __future__ import annotations

import asyncio
import re
import time

from controlplane_detectors._models import detoxify_model, regard_classifier
from controlplane_detectors.base import (
    Category,
    DetectionResult,
    Detector,
    DetectorContext,
    Severity,
)

# Paired terms for the demographic-swap differential. Each axis maps a text to a
# counterfactual; a large regard gap between the two is a bias signal.
_SWAP_AXES: dict[str, list[tuple[str, str]]] = {
    "gender": [
        ("he", "she"),
        ("him", "her"),
        ("his", "her"),
        ("man", "woman"),
        ("men", "women"),
        ("male", "female"),
        ("father", "mother"),
        ("boy", "girl"),
        ("mr", "ms"),
    ],
    "religion": [
        ("christian", "muslim"),
        ("christians", "muslims"),
        ("church", "mosque"),
        ("jewish", "hindu"),
    ],
    "race": [
        ("white", "black"),
        ("european", "african"),
        ("western", "asian"),
    ],
}

_TOX_HIGH = 0.8
_TOX_MEDIUM = 0.5
_TOX_LOW = 0.2
_REGARD_GAP_HIGH = 0.5
_REGARD_GAP_MEDIUM = 0.3


def _swap_terms(text: str, pairs: list[tuple[str, str]]) -> str:
    """Bidirectional, case-preserving whole-word substitution."""

    lookup: dict[str, str] = {}
    for a, b in pairs:
        lookup[a] = b
        lookup[b] = a

    def repl(m: re.Match[str]) -> str:
        word = m.group(0)
        sub = lookup[word.lower()]
        if word.isupper():
            return sub.upper()
        if word[0].isupper():
            return sub.capitalize()
        return sub

    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in lookup) + r")\b", re.IGNORECASE)
    return pattern.sub(repl, text)


def _negative_regard(scores: list[dict]) -> float:
    for entry in scores:
        if entry["label"] == "negative":
            return float(entry["score"])
    return 0.0


class ToxicityBiasDetector(Detector):
    name = "toxicity_bias.detoxify+regard"
    check = "toxicity"

    async def analyze(self, text: str, context: DetectorContext) -> DetectionResult:
        started = time.perf_counter()

        try:
            tox = await asyncio.to_thread(detoxify_model().predict, text)
        except Exception as exc:
            return DetectionResult.failed(self.name, f"detoxify unavailable: {exc}")
        tox = {k: float(v) for k, v in tox.items()}
        tox_max = max(tox.values())
        tox_worst = max(tox, key=lambda k: tox[k])

        regard_available = True
        regard_reason = ""
        regard_negative = 0.0
        regard_gap = 0.0
        gap_axis: str | None = None
        try:
            variants = [text]
            axes: list[str] = []
            for axis, pairs in _SWAP_AXES.items():
                swapped = _swap_terms(text, pairs)
                if swapped != text:
                    variants.append(swapped)
                    axes.append(axis)
            batched = await asyncio.to_thread(regard_classifier(), variants)
            regard_negative = _negative_regard(batched[0])
            for axis, scored in zip(axes, batched[1:], strict=True):
                gap = abs(_negative_regard(scored) - regard_negative)
                if gap > regard_gap:
                    regard_gap, gap_axis = gap, axis
        except Exception as exc:
            regard_available = False
            regard_reason = str(exc)

        # --- severity ---
        categories: list[Category] = []
        if tox_max >= _TOX_LOW:
            categories.append(Category.TOXICITY)
        if tox.get("identity_attack", 0.0) >= _TOX_MEDIUM or regard_gap >= _REGARD_GAP_MEDIUM:
            categories.append(Category.BIAS)

        tox_sev = (
            Severity.HIGH
            if tox_max >= _TOX_HIGH
            else Severity.MEDIUM
            if tox_max >= _TOX_MEDIUM
            else Severity.LOW
            if tox_max >= _TOX_LOW
            else Severity.NONE
        )
        bias_sev = (
            Severity.HIGH
            if regard_gap >= _REGARD_GAP_HIGH
            else Severity.MEDIUM
            if regard_gap >= _REGARD_GAP_MEDIUM
            else Severity.NONE
        )
        severity = max(tox_sev, bias_sev, key=_SEV_ORDER.__getitem__)

        # --- confidence: the two signals agreeing raises it, disagreement lowers it ---
        tox_flags_identity = tox.get("identity_attack", 0.0) >= _TOX_MEDIUM
        bias_flagged = regard_gap >= _REGARD_GAP_MEDIUM
        if not regard_available:
            confidence = min(0.6, tox_max) if severity != Severity.NONE else 0.5
            rationale_tail = f" regard signal unavailable ({regard_reason}); confidence capped"
        elif severity == Severity.NONE:
            confidence = 0.85
            rationale_tail = ""
        elif tox_flags_identity == bias_flagged:
            confidence = round(min(0.95, 0.6 + tox_max / 2 + regard_gap / 2), 3)
            rationale_tail = ""
        else:
            confidence = 0.5
            rationale_tail = " toxicity and regard signals disagree; confidence reduced"

        rationale = (
            f"detoxify {tox_worst}={tox_max:.2f}; "
            f"regard negative={regard_negative:.2f}, "
            f"max swap gap={regard_gap:.2f}"
            + (f" ({gap_axis})" if gap_axis else "")
            + rationale_tail
        )

        return DetectionResult(
            detector=self.name,
            ok=True,
            categories=categories,
            severity=severity,
            confidence=confidence,
            evidence={
                "detoxify": {k: round(v, 4) for k, v in tox.items()},
                "regard_available": regard_available,
                "regard_negative": round(regard_negative, 4),
                "regard_swap_gap": round(regard_gap, 4),
                "regard_swap_axis": gap_axis,
            },
            rationale=rationale,
            latency_ms=(time.perf_counter() - started) * 1000,
        )


_SEV_ORDER = {Severity.NONE: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}
