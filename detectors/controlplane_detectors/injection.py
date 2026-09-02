"""Prompt injection detector.

Analyzes the incoming prompt (and source documents) for jailbreak attempts,
rather than just the model's output. Uses a combination of regex heuristics
and embedding similarity against a known bank of prompt injections.
"""

from __future__ import annotations

import logging
import re

from controlplane_detectors import (
    Category,
    DetectionResult,
    Detector,
    DetectorContext,
    Severity,
    Span,
    _models,
)

log = logging.getLogger(__name__)

# Heuristic patterns
_HEURISTICS_HIGH = [
    r"ignore (?:all|any|the) previous instructions",
    r"disregard (?:your|the) system prompt",
    r"you (?:are|have) no (?:restrictions|rules|filters) now",
    r"act as DAN",
    r"developer mode",
    r"jailbreak",
    r"reveal your (?:system prompt|instructions)",
    r"print your instructions",
    r"pretend you (?:are|have) no (?:guidelines|restrictions)",
    r"system prompt:",
]

_HEURISTICS_MEDIUM = [
    r"hypothetically",
    r"for a fictional story where there are no rules",
    r"let's roleplay that you are an AI without",
    r"this is just a test, ignore safety",
]

_HIGH_RE = re.compile("|".join(_HEURISTICS_HIGH), re.IGNORECASE)
_MED_RE = re.compile("|".join(_HEURISTICS_MEDIUM), re.IGNORECASE)

# Similarity thresholds
_SIM_HIGH = 0.85
_SIM_MEDIUM = 0.75
_SIM_LOW = 0.60


class InjectionDetector(Detector):
    name = "injection.heuristics+embed_sim"
    check = "injection"

    async def analyze(self, text: str, context: DetectorContext) -> DetectionResult:
        # 1. Honest degradation if there's nothing to check.
        if not context.prompt and not context.source_documents:
            return DetectionResult(
                detector=self.name,
                ok=True,
                severity=Severity.NONE,
                evidence={"assessable": False},
                rationale="no prompt or source documents to analyze",
            )

        try:
            spans = []
            has_high_heuristic = False
            has_med_heuristic = False

            # Text to scan with regexes: prompt + sources + output text (for compliance markers)
            texts_to_scan = [context.prompt or ""] + context.source_documents + [text]
            combined_text = " ".join(t for t in texts_to_scan if t)

            # Evaluate heuristics
            for match in _HIGH_RE.finditer(combined_text):
                has_high_heuristic = True
                spans.append(
                    Span(
                        start=match.start(),
                        end=match.end(),
                        text=match.group(),
                        label="heuristic_high",
                    )
                )

            for match in _MED_RE.finditer(combined_text):
                has_med_heuristic = True
                spans.append(
                    Span(
                        start=match.start(),
                        end=match.end(),
                        text=match.group(),
                        label="heuristic_medium",
                    )
                )

            # Evaluate embeddings
            sim_score = 0.0
            embedder_failed = False
            embedder_reason = ""

            texts_to_embed = [context.prompt] if context.prompt else []
            texts_to_embed.extend(context.source_documents)

            if texts_to_embed:
                try:
                    import torch
                    from sentence_transformers import util

                    embedder = _models.injection_embedder()
                    bank_embeddings = _models.injection_bank_embeddings()

                    query_embeddings = embedder.encode(texts_to_embed, convert_to_tensor=True)
                    # compute cosine similarities: (num_queries, num_bank_entries)
                    cosine_scores = util.cos_sim(query_embeddings, bank_embeddings)
                    # take max across all queries and bank entries
                    sim_score = float(torch.max(cosine_scores))
                except Exception as exc:
                    log.warning("Injection embedder failed: %r", exc)
                    embedder_failed = True
                    embedder_reason = f"embedder failed: {exc!r}"

            # Combine signals
            has_high_sim = sim_score >= _SIM_HIGH
            has_med_sim = sim_score >= _SIM_MEDIUM
            has_low_sim = sim_score >= _SIM_LOW

            severity = Severity.NONE
            if has_high_heuristic or has_high_sim:
                severity = Severity.HIGH
            elif has_med_heuristic or has_med_sim:
                severity = Severity.MEDIUM
            elif has_low_sim:
                severity = Severity.LOW

            # Compute confidence
            confidence = 0.0
            if severity != Severity.NONE:
                if embedder_failed:
                    confidence = 0.5  # Cap confidence
                else:
                    heuristic_fired = has_high_heuristic or has_med_heuristic
                    sim_fired = has_high_sim or has_med_sim or has_low_sim

                    if heuristic_fired and sim_fired:
                        confidence = 0.95
                    else:
                        confidence = 0.65

            categories = [Category.INJECTION] if severity != Severity.NONE else []
            evidence = {"max_similarity": sim_score}
            if embedder_failed:
                evidence["embedder_error"] = embedder_reason

            rationale = (
                "injection signals detected"
                if severity != Severity.NONE
                else "no injection detected"
            )
            if embedder_failed:
                rationale += f" (Note: {embedder_reason})"

            return DetectionResult(
                detector=self.name,
                ok=True,
                categories=categories,
                severity=severity,
                confidence=confidence,
                spans=spans,
                evidence=evidence,
                rationale=rationale,
            )
        except Exception as exc:
            # Only ok=False if the overall control flow fails, not if just the embedder fails.
            return DetectionResult.failed(self.name, f"injection detector raised: {exc!r}")
