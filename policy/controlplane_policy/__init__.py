"""ControlPlane.ai policy engine.

Behaviour is data, not code branches: policy packs are versioned YAML, resolved
per request into a content-hashed :class:`EffectivePolicy` that every audit
record cites.
"""

from controlplane_policy.hashing import content_hash, version_label
from controlplane_policy.loader import PolicyLoadError, PolicyRepo
from controlplane_policy.resolver import PolicyEngine, PolicyResolutionError, deep_merge
from controlplane_policy.schema import (
    ActionConfig,
    ActionPolicy,
    CheckConfig,
    DecisionRule,
    EffectivePolicy,
    LatencyPath,
    PiiHandling,
    PolicyMeta,
    Severity,
    Tier,
)

__all__ = [
    "ActionConfig",
    "ActionPolicy",
    "CheckConfig",
    "DecisionRule",
    "EffectivePolicy",
    "LatencyPath",
    "PiiHandling",
    "PolicyEngine",
    "PolicyLoadError",
    "PolicyMeta",
    "PolicyRepo",
    "PolicyResolutionError",
    "Severity",
    "Tier",
    "content_hash",
    "deep_merge",
    "version_label",
]
