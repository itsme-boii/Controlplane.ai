"""Load policy packs from a directory tree.

Layout::

    policies/
      base.yaml
      usecases/<id>.yaml
      jurisdictions/<geo>.yaml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_KNOWN_TOP_LEVEL = {
    "meta",
    "latency_path",
    "latency_budget_ms",
    "confidence_floor",
    "checks",
    "pii",
    "decision_rules",
    "retention_days",
    "action_policy",
}

_KNOWN_ACTION_POLICY = {"enabled", "actions"}
_KNOWN_ACTION_CONFIG = {"min_confidence", "max_text_tier", "block_if_ledger_escalated"}


class PolicyLoadError(ValueError):
    pass


class PolicyRepo:
    """In-memory view of a policies/ directory. Raw dicts only — validation of
    the *merged* result happens in the resolver."""

    def __init__(
        self,
        base: dict[str, Any],
        usecases: dict[str, dict],
        jurisdictions: dict[str, dict],
    ):
        self.base = base
        self.usecases = usecases
        self.jurisdictions = jurisdictions

    @classmethod
    def from_dir(cls, root: str | Path) -> PolicyRepo:
        root = Path(root)
        if not root.is_dir():
            raise PolicyLoadError(f"policy directory not found: {root}")

        base_path = root / "base.yaml"
        if not base_path.exists():
            raise PolicyLoadError(f"missing base policy: {base_path}")
        base = _read_pack(base_path, expected_kind="base")

        usecases = {
            p.stem: _read_pack(p, expected_kind="usecase")
            for p in sorted((root / "usecases").glob("*.yaml"))
        }
        jurisdictions = {
            p.stem: _read_pack(p, expected_kind="jurisdiction")
            for p in sorted((root / "jurisdictions").glob("*.yaml"))
        }
        return cls(base, usecases, jurisdictions)


def _read_pack(path: Path, *, expected_kind: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise PolicyLoadError(f"{path}: invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise PolicyLoadError(f"{path}: top level must be a mapping")

    unknown = set(data) - _KNOWN_TOP_LEVEL
    if unknown:
        raise PolicyLoadError(f"{path}: unknown keys {sorted(unknown)}")

    action_policy = data.get("action_policy")
    if isinstance(action_policy, dict):
        unknown_ap = set(action_policy) - _KNOWN_ACTION_POLICY
        if unknown_ap:
            raise PolicyLoadError(f"{path}: action_policy: unknown keys {sorted(unknown_ap)}")
        actions = action_policy.get("actions")
        if isinstance(actions, dict):
            for action_name, action_cfg in actions.items():
                if not isinstance(action_cfg, dict):
                    continue
                unknown_cfg = set(action_cfg) - _KNOWN_ACTION_CONFIG
                if unknown_cfg:
                    raise PolicyLoadError(
                        f"{path}: action_policy.actions.{action_name}: "
                        f"unknown keys {sorted(unknown_cfg)}"
                    )

    kind = data.get("meta", {}).get("kind")
    if kind != expected_kind:
        raise PolicyLoadError(f"{path}: meta.kind is {kind!r}, expected {expected_kind!r}")

    return data
