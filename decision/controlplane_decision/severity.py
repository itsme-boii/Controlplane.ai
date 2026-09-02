"""Severity ordering, shared by the aggregator and the rule evaluator.

The detector library and the policy schema each define their own ``Severity``
StrEnum with identical members; the engine consumes detector results, so it uses
the detector one and compares by this rank.
"""

from __future__ import annotations

from controlplane_detectors import Severity

RANK: dict[Severity, int] = {
    Severity.NONE: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
}


def at_least(value: Severity, floor: Severity) -> bool:
    return RANK[value] >= RANK[floor]


def worst(*values: Severity) -> Severity:
    return max(values, key=RANK.__getitem__, default=Severity.NONE)
