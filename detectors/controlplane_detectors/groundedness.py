"""Groundedness detector — claim extraction + cross-encoder NLI entailment.

The answer is split into sentence-level claims (spaCy). Each claim is checked
against the supplied source documents with a cross-encoder NLI model
(premise = source passage, hypothesis = claim):

* contradiction -> the sources say otherwise  -> HALLUCINATION
* neutral       -> sources neither confirm nor deny -> UNSUPPORTED
* entailment    -> grounded

With no source documents the detector abstains: it reports that groundedness is
not assessable rather than guessing a safe-looking answer.
"""

from __future__ import annotations

import asyncio
import math
import time

from controlplane_detectors._models import nli_cross_encoder, spacy_nlp
from controlplane_detectors.base import (
    Category,
    DetectionResult,
    Detector,
    DetectorContext,
    Severity,
    Span,
)

_ENTAIL_MIN = 0.60
_CONTRADICT_MIN = 0.60
_PASSAGE_SENTENCES = 3
_MIN_CLAIM_TOKENS = 4
# NLI logit order for cross-encoder/nli-deberta-v3-xsmall.
_LABELS = ("contradiction", "entailment", "neutral")


def _softmax(row: list[float]) -> list[float]:
    hi = max(row)
    exps = [math.exp(v - hi) for v in row]
    total = sum(exps)
    return [v / total for v in exps]


def _passages(doc_text: str, nlp) -> list[str]:
    sents = [s.text.strip() for s in nlp(doc_text).sents if s.text.strip()]
    if not sents:
        return [doc_text.strip()] if doc_text.strip() else []
    return [
        " ".join(sents[i : i + _PASSAGE_SENTENCES])
        for i in range(0, len(sents), _PASSAGE_SENTENCES)
    ]


class GroundednessDetector(Detector):
    name = "groundedness.nli"
    check = "groundedness"

    async def analyze(self, text: str, context: DetectorContext) -> DetectionResult:
        started = time.perf_counter()
        sources = [d for d in context.source_documents if d and d.strip()]

        if not sources:
            return DetectionResult(
                detector=self.name,
                ok=True,
                severity=Severity.NONE,
                confidence=0.0,
                evidence={"assessable": False},
                rationale="no source documents supplied; groundedness not assessable",
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        try:
            nlp = spacy_nlp()
            model = nli_cross_encoder()
            passages: list[str] = []
            for src in sources:
                passages.extend(_passages(src, nlp))

            claims: list[tuple[int, int, str]] = []
            for sent in nlp(text).sents:
                s = sent.text.strip()
                if len(sent) >= _MIN_CLAIM_TOKENS and not s.endswith("?"):
                    claims.append((sent.start_char, sent.end_char, s))

            if not claims or not passages:
                return DetectionResult(
                    detector=self.name,
                    ok=True,
                    severity=Severity.NONE,
                    confidence=0.0,
                    evidence={"assessable": False},
                    rationale="no verifiable claims / passages extracted",
                    latency_ms=(time.perf_counter() - started) * 1000,
                )

            pairs = [(p, claim) for (_, _, claim) in claims for p in passages]
            logits = await asyncio.to_thread(model.predict, pairs)
        except Exception as exc:
            return DetectionResult.failed(self.name, f"nli groundedness unavailable: {exc}")

        # Reduce each claim to its best-supporting and most-contradicting passage.
        per_claim = []
        spans: list[Span] = []
        idx = 0
        worst = Severity.NONE
        confidences: list[float] = []
        for start, end, claim in claims:
            best_entail = 0.0
            best_contra = 0.0
            for _ in passages:
                probs = _softmax(list(logits[idx]))
                best_entail = max(best_entail, probs[_LABELS.index("entailment")])
                best_contra = max(best_contra, probs[_LABELS.index("contradiction")])
                idx += 1
            if best_contra >= _CONTRADICT_MIN and best_contra >= best_entail:
                verdict = "contradicted"
                worst = Severity.HIGH
                spans.append(Span(start=start, end=end, text=claim, label="contradicted"))
                confidences.append(best_contra)
            elif best_entail >= _ENTAIL_MIN:
                verdict = "grounded"
                confidences.append(best_entail)
            else:
                verdict = "unsupported"
                worst = max(worst, Severity.LOW, key=_SEV_ORDER.__getitem__)
                spans.append(Span(start=start, end=end, text=claim, label="unsupported"))
                confidences.append(max(best_entail, best_contra, 0.5))
            per_claim.append(
                {
                    "claim": claim,
                    "verdict": verdict,
                    "entailment": round(best_entail, 3),
                    "contradiction": round(best_contra, 3),
                }
            )

        unsupported = sum(1 for c in per_claim if c["verdict"] == "unsupported")
        contradicted = sum(1 for c in per_claim if c["verdict"] == "contradicted")
        if not contradicted and unsupported and unsupported / len(per_claim) >= 0.5:
            worst = max(worst, Severity.MEDIUM, key=_SEV_ORDER.__getitem__)

        categories = [Category.HALLUCINATION] if worst != Severity.NONE else []
        return DetectionResult(
            detector=self.name,
            ok=True,
            categories=categories,
            severity=worst,
            confidence=round(sum(confidences) / len(confidences), 3),
            spans=spans,
            evidence={
                "assessable": True,
                "claims_total": len(per_claim),
                "contradicted": contradicted,
                "unsupported": unsupported,
                "per_claim": per_claim,
            },
            rationale=(
                f"{len(per_claim)} claim(s): {contradicted} contradicted, "
                f"{unsupported} unsupported by {len(sources)} source doc(s)"
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


_SEV_ORDER = {Severity.NONE: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}
