import pytest

from controlplane_policy import PolicyResolutionError, Tier
from controlplane_policy.resolver import deep_merge

# --- deep_merge unit behaviour -------------------------------------------------


def test_deep_merge_recurses_maps_and_replaces_scalars():
    base = {"a": 1, "nested": {"x": 1, "y": 2}, "list": [1, 2]}
    overlay = {"a": 2, "nested": {"y": 9, "z": 3}, "list": [3]}
    assert deep_merge(base, overlay) == {
        "a": 2,
        "nested": {"x": 1, "y": 9, "z": 3},
        "list": [3],
    }


def test_deep_merge_does_not_mutate_inputs():
    base = {"nested": {"x": 1}}
    deep_merge(base, {"nested": {"x": 2}})
    assert base == {"nested": {"x": 1}}


# --- resolution --------------------------------------------------------------


def test_base_only_resolves(engine):
    p = engine.resolve(None, None)
    assert p.meta.name == "base"
    assert p.resolved_from == ["base"]
    assert p.latency_path.value == "deep"


def test_usecase_overrides_base(engine):
    p = engine.resolve("supportassist", None)
    assert p.latency_path.value == "fast"
    assert p.latency_budget_ms == 400
    assert p.checks["groundedness"].enabled is False  # disabled by the use case
    assert p.checks["pii"].enabled is True  # inherited from base


def test_case_insensitive_and_whitespace_tolerant(engine):
    p = engine.resolve("  SupportAssist ", " US ")
    assert p.meta.name == "supportassist+us"
    assert p.meta.kind == "effective"
    assert p.resolved_from == ["base", "usecase:supportassist", "jurisdiction:us"]


def test_unknown_usecase_raises(engine):
    with pytest.raises(PolicyResolutionError, match="unknown use case"):
        engine.resolve("does-not-exist", None)


def test_unknown_jurisdiction_raises(engine):
    with pytest.raises(PolicyResolutionError, match="unknown jurisdiction"):
        engine.resolve("supportassist", "antarctica")


# --- conflicting-rule cases (required by the phase exit criteria) -----------


def test_eu_overlay_wins_over_usecase_on_conflict(engine):
    """supportassist sets judge.blocking = false (fast path, post-hoc judge).
    The EU overlay sets judge.blocking = true (AI Act: human oversight).
    Applied last, EU must win."""
    us = engine.resolve("supportassist", "us")
    eu = engine.resolve("supportassist", "eu")
    assert us.checks["judge"].blocking is False
    assert eu.checks["judge"].blocking is True


def test_eu_overlay_changes_pii_action(engine):
    """base + use case say pii.action = edit; EU says review. EU wins."""
    assert engine.resolve("knowledgecopilot", "us").pii.action is Tier.EDIT
    assert engine.resolve("knowledgecopilot", "eu").pii.action is Tier.REVIEW


def test_eu_overlay_tightens_thresholds(engine):
    us = engine.resolve("knowledgecopilot", "us")
    eu = engine.resolve("knowledgecopilot", "eu")
    assert eu.checks["pii"].thresholds["score"] < us.checks["pii"].thresholds["score"]
    assert eu.confidence_floor < us.confidence_floor or eu.confidence_floor == 0.65


def test_decisionsupport_replaces_decision_table(engine):
    p = engine.resolve("decisionsupport", "us")
    bias_block = [
        r for r in p.decision_rules if r.when.get("category") == "bias" and r.tier is Tier.BLOCK
    ]
    assert bias_block, "decisionsupport should block medium-severity bias outright"


# --- versioning ------------------------------------------------------------


def test_version_is_stable_and_context_specific(engine):
    a = engine.resolve("knowledgecopilot", "us")
    b = engine.resolve("knowledgecopilot", "us")
    c = engine.resolve("knowledgecopilot", "eu")
    assert a.version == b.version
    assert a.version != c.version
    assert a.version.startswith("knowledgecopilot+us:")


def test_snapshot_round_trips_to_same_hash(engine):
    from controlplane_policy.hashing import content_hash

    p = engine.resolve("decisionsupport", "eu")
    snapshot = p.model_dump(mode="json", exclude={"version", "resolved_from"})
    # Re-hashing the stored snapshot reproduces the recorded version id.
    assert content_hash(snapshot)[:12] == p.version.split(":")[1]

# --- action_policy ------------------------------------------------------------

def test_action_policy_deep_merges(engine):
    base_us = engine.resolve(None, "us")
    assert base_us.action_policy.enabled is True
    assert "send_email" in base_us.action_policy.actions
    assert base_us.action_policy.actions["default"].min_confidence == 0.9
    
    ds_us = engine.resolve("decisionsupport", "us")
    assert ds_us.action_policy.enabled is True
    assert ds_us.action_policy.actions["default"].min_confidence == 0.99
    # The send_email block is inherited from base.yaml
    assert "send_email" in ds_us.action_policy.actions
