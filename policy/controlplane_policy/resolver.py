"""Resolve (use-case id, jurisdiction) -> a single hashed EffectivePolicy."""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any

from controlplane_policy.hashing import version_label
from controlplane_policy.loader import PolicyRepo
from controlplane_policy.schema import EffectivePolicy


class PolicyResolutionError(ValueError):
    pass


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overlay`` onto ``base``. Nested mappings merge key by
    key; every other value (scalar, list) is replaced wholesale. An overlay that
    mentions ``decision_rules`` therefore replaces the whole table, not appends —
    a deliberate choice so a stricter jurisdiction can fully restate the rules.
    """
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


class PolicyEngine:
    def __init__(self, repo: PolicyRepo) -> None:
        self._repo = repo

    @property
    def usecases(self) -> list[str]:
        return sorted(self._repo.usecases)

    @property
    def jurisdictions(self) -> list[str]:
        return sorted(self._repo.jurisdictions)

    def resolve(self, usecase_id: str | None, jurisdiction: str | None) -> EffectivePolicy:
        layers: list[tuple[str, dict]] = [("base", self._repo.base)]
        label_parts: list[str] = []

        uc_key = _norm(usecase_id)
        if uc_key:
            if uc_key not in self._repo.usecases:
                raise PolicyResolutionError(f"unknown use case: {usecase_id!r}")
            layers.append((f"usecase:{uc_key}", self._repo.usecases[uc_key]))
            label_parts.append(uc_key)

        geo_key = _norm(jurisdiction)
        if geo_key:
            if geo_key not in self._repo.jurisdictions:
                raise PolicyResolutionError(f"unknown jurisdiction: {jurisdiction!r}")
            layers.append((f"jurisdiction:{geo_key}", self._repo.jurisdictions[geo_key]))
            label_parts.append(geo_key)

        # `meta` describes a single file; a merged policy needs its own. Strip it
        # from every layer and synthesize one from the resolution context.
        merged: dict[str, Any] = {}
        max_effective = dt.date.min
        for _, layer in layers:
            layer_meta = layer.get("meta", {})
            eff = layer_meta.get("effective_from")
            if isinstance(eff, dt.date):
                max_effective = max(max_effective, eff)
            merged = deep_merge(merged, {k: v for k, v in layer.items() if k != "meta"})

        label = "+".join(label_parts) or "base"
        merged["meta"] = {
            "name": label,
            "kind": "effective",
            "description": f"resolved: {' <- '.join(name for name, _ in layers)}",
            "effective_from": max_effective,
        }

        try:
            policy = EffectivePolicy.model_validate(merged)
        except Exception as exc:  # pydantic ValidationError -> our error type
            raise PolicyResolutionError(
                f"merged policy for ({usecase_id}, {jurisdiction}) is invalid: {exc}"
            ) from exc

        # Identity is derived from the *validated* policy so that re-hashing the
        # snapshot stored in an audit record reproduces this exact version id.
        content = policy.model_dump(mode="json", exclude={"version", "resolved_from"})
        policy.version = version_label(label, content)
        policy.resolved_from = [name for name, _ in layers]
        return policy


def _norm(value: str | None) -> str | None:
    return value.strip().lower() or None if value else None
