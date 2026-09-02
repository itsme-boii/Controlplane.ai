"""Evaluate the policy's decision table against an assessment.

The table is ``policy.decision_rules`` — an ordered list of ``{when, tier, note}``
rows, authored in YAML, carried verbatim through policy resolution. Rules are
tried top to bottom; the first whose ``when`` matches decides the tier. The
engine adds no implicit rows here — fail-safe behaviour lives in ``engine.py``
so it cannot be weakened by editing a policy.

Supported ``when`` predicates (a row's keys are AND-ed together):

===========================  ====================================================
``always: true``             matches unconditionally (use as the last row)
``category: <token>``        a finding in this category exists; ``any`` = any category
``min_severity: <level>``    severity ≥ level (of ``category`` if given, else the max)
``only: true``               with ``category``: that category is the *only* one present
``detector_failed: true``    at least one detector returned ``ok is False``
``confidence_below: <x>``    overall assessment confidence < x
===========================  ====================================================

Category tokens are the :class:`Category` values plus ``groundedness`` as an
alias for ``hallucination`` (the check is named "groundedness"; the category it
raises is "hallucination").
"""

from __future__ import annotations

from typing import Any

from controlplane_detectors import Category, Severity
from controlplane_policy import EffectivePolicy, Tier
from pydantic import BaseModel

from controlplane_decision.aggregate import Assessment
from controlplane_decision.severity import at_least

_CATEGORY_ALIAS = {"groundedness": Category.HALLUCINATION}

_KNOWN_KEYS = {
    "always",
    "category",
    "min_severity",
    "only",
    "detector_failed",
    "confidence_below",
    "note",
}


class RuleError(ValueError):
    """A decision rule uses a predicate or value the engine does not understand.
    Raised rather than silently skipped — an unenforceable rule is a policy bug."""


class RuleMatch(BaseModel):
    index: int | None  # position in decision_rules, or None when none matched
    tier: Tier
    note: str
    exhausted: bool = False  # True when the table ran out with no match


def _category(token: str) -> Category | None:
    if token == "any":
        return None
    if token in _CATEGORY_ALIAS:
        return _CATEGORY_ALIAS[token]
    try:
        return Category(token)
    except ValueError as exc:
        raise RuleError(f"unknown category token: {token!r}") from exc


def _severity(token: str) -> Severity:
    try:
        return Severity(token)
    except ValueError as exc:
        raise RuleError(f"unknown severity: {token!r}") from exc


def _matches(when: dict[str, Any], assessment: Assessment) -> bool:
    unknown = set(when) - _KNOWN_KEYS
    if unknown:
        raise RuleError(f"unknown predicate key(s): {sorted(unknown)}")
    if not set(when) - {"note"}:
        raise RuleError("empty rule predicate")

    if when.get("always") is True:
        return True

    if when.get("detector_failed") is True and not assessment.failed_detectors:
        return False

    if "confidence_below" in when and not (assessment.confidence < float(when["confidence_below"])):
        return False

    cat_token = when.get("category")
    if cat_token is not None:
        category = _category(str(cat_token))
        floor = _severity(str(when.get("min_severity", "low")))
        if category is None:  # "any"
            if not at_least(assessment.max_severity, floor):
                return False
        else:
            risk = assessment.risks.get(category)
            if risk is None or not at_least(risk.severity, floor):
                return False
            if when.get("only") is True and not assessment.has_only(category):
                return False
    elif "min_severity" in when:
        if not at_least(assessment.max_severity, _severity(str(when["min_severity"]))):
            return False
    elif "only" in when:
        raise RuleError("`only` requires `category`")

    return True


def evaluate(assessment: Assessment, policy: EffectivePolicy) -> RuleMatch:
    for index, rule in enumerate(policy.decision_rules):
        if _matches(rule.when, assessment):
            return RuleMatch(index=index, tier=rule.tier, note=rule.note)
    # No row matched. The engine turns this into `review` — never `allow`.
    return RuleMatch(index=None, tier=Tier.REVIEW, note="decision table exhausted", exhausted=True)


def lint_table(policy: EffectivePolicy) -> None:
    """Validate every predicate up front so a broken rule fails at load time,
    not on the one request that would have matched it."""
    empty = Assessment()
    for rule in policy.decision_rules:
        _matches(rule.when, empty)
