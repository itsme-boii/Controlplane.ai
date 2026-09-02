import pytest

from controlplane_policy import PolicyLoadError, PolicyRepo
from controlplane_policy.loader import _read_pack


def test_loads_shipped_packs(engine):
    assert set(engine.usecases) == {"decisionsupport", "knowledgecopilot", "supportassist"}
    assert set(engine.jurisdictions) == {"eu", "us"}


def test_missing_dir_raises(tmp_path):
    with pytest.raises(PolicyLoadError):
        PolicyRepo.from_dir(tmp_path / "nope")


def test_unknown_top_level_key_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("meta:\n  name: x\n  kind: base\n  effective_from: 2026-01-01\ntypo_here: 1\n")
    with pytest.raises(PolicyLoadError, match="unknown keys"):
        _read_pack(p, expected_kind="base")


def test_wrong_kind_rejected(tmp_path):
    p = tmp_path / "us.yaml"
    p.write_text("meta:\n  name: us\n  kind: base\n  effective_from: 2026-01-01\n")
    with pytest.raises(PolicyLoadError, match="expected 'jurisdiction'"):
        _read_pack(p, expected_kind="jurisdiction")

def test_unknown_action_policy_key_rejected(tmp_path):
    p = tmp_path / "bad_action.yaml"
    p.write_text(
        "meta:\n  name: x\n  kind: base\n  effective_from: 2026-01-01\n"
        "action_policy:\n  typo_here: 1\n"
    )
    with pytest.raises(PolicyLoadError, match="unknown keys"):
        _read_pack(p, expected_kind="base")
