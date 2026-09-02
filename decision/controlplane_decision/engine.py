"""The decision engine: detector findings + effective policy -> one tiered decision.

Pipeline (pure, synchronous — detectors have already run):

1. **Aggregate** the raw :class:`DetectionResult` list into a per-category
   :class:`Assessment`.
2. **Evaluate** the policy's decision table against it (``rules.evaluate``).
3. **Fail-safe overrides** — applied *after* the table and independent of how a
   policy is authored, so the no-false-fallback rule holds even if a policy
   forgets a rule:
   - any detector that could not complete -> never ``allow``/``edit``; escalate
     to ``review``;
   - the table matched no row -> ``review``;
   - final tier ``allow`` but overall confidence below the policy's
     ``confidence_floor`` -> ``review``;
   - final tier ``edit`` but there is nothing we are allowed to mask ->
     ``review`` (we will not return a response we promised to sanitise but did
     not).
4. For a surviving ``edit`` tier, compute the redaction.

Every override sets ``fail_safe_triggered`` and records why in ``rationale``.
"""

from __future__ import annotations

from controlplane_detectors import Category, DetectionResult
from controlplane_policy import EffectivePolicy, Tier
from pydantic import BaseModel, Field

from controlplane_decision.aggregate import Assessment, aggregate
from controlplane_decision.redact import RedactionOutcome, redact_spans
from controlplane_decision.rules import RuleMatch, evaluate

_NON_FINAL = {Tier.ALLOW, Tier.EDIT}


class Decision(BaseModel):
    tier: Tier
    rule_index: int | None
    rule_note: str
    confidence: float
    fail_safe_triggered: bool = False
    assessment: Assessment
    redaction: RedactionOutcome | None = None
    rationale: str = ""
    reasons: list[str] = Field(default_factory=list)

    @property
    def released_text_allowed(self) -> bool:
        """Whether the model's output (verbatim or redacted) may be returned to
        the caller. ``review`` and ``block`` hold it back."""
        return self.tier in (Tier.ALLOW, Tier.EDIT)


class DecisionEngine:
    def decide(
        self, analysed_text: str, results: list[DetectionResult], policy: EffectivePolicy
    ) -> Decision:
        assessment = aggregate(results, policy)
        match: RuleMatch = evaluate(assessment, policy)

        tier = match.tier
        reasons: list[str] = []
        fail_safe = False

        if match.exhausted:
            reasons.append("decision table matched no rule; defaulting to review")
            fail_safe = True

        if assessment.failed_detectors and tier in _NON_FINAL:
            reasons.append(
                "detector(s) could not complete "
                f"({', '.join(assessment.failed_detectors)}); missing evidence never allows"
            )
            tier = Tier.REVIEW
            fail_safe = True

        if tier is Tier.ALLOW and assessment.confidence < policy.confidence_floor:
            reasons.append(
                f"confidence {assessment.confidence:.2f} below policy floor "
                f"{policy.confidence_floor:.2f}"
            )
            tier = Tier.REVIEW
            fail_safe = True

        redaction: RedactionOutcome | None = None
        if tier is Tier.EDIT:
            pii_risk = assessment.risks.get(Category.PII)
            spans = pii_risk.spans if pii_risk else []
            redaction = redact_spans(analysed_text, spans, policy.pii)
            if not redaction.changed:
                reasons.append(
                    "edit tier selected but no maskable span is available; "
                    "cannot sanitise the response as promised"
                )
                tier = Tier.REVIEW
                redaction = None
                fail_safe = True

        rule_desc = "fallback" if match.index is None else f"rule #{match.index}"
        head = match.note or rule_desc
        rationale = f"{tier.value}: {head}"
        if reasons:
            rationale += " — " + "; ".join(reasons)

        return Decision(
            tier=tier,
            rule_index=match.index,
            rule_note=match.note,
            confidence=assessment.confidence,
            fail_safe_triggered=fail_safe,
            assessment=assessment,
            redaction=redaction,
            rationale=rationale,
            reasons=reasons,
        )
