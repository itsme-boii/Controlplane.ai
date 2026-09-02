"""ControlPlane.ai decision engine.

Turns the detector library's :class:`DetectionResult` list plus a resolved
:class:`EffectivePolicy` into one tiered decision (allow / edit / review / block)
with the evidence attached and the no-false-fallback rule enforced structurally.
"""

from controlplane_decision.aggregate import Assessment, CategoryRisk, aggregate
from controlplane_decision.engine import Decision, DecisionEngine
from controlplane_decision.redact import MaskedSpan, RedactionOutcome, redact_spans
from controlplane_decision.rules import RuleError, RuleMatch, evaluate, lint_table

__all__ = [
    "Assessment",
    "CategoryRisk",
    "Decision",
    "DecisionEngine",
    "MaskedSpan",
    "RedactionOutcome",
    "RuleError",
    "RuleMatch",
    "aggregate",
    "evaluate",
    "lint_table",
    "redact_spans",
]
