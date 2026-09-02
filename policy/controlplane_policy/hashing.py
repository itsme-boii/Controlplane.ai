"""Content-addressed policy versions.

Every resolved policy gets a deterministic id derived from its content, so an
audit record can cite *exactly* which policy decided — and anyone can recompute
the hash from the stored snapshot to prove it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(data: Any) -> str:
    """Stable serialization: sorted keys, no incidental whitespace."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def version_label(name: str, data: Any) -> str:
    """e.g. ``knowledgecopilot@eu:1a2b3c4d`` — human-readable, still unique."""
    return f"{name}:{content_hash(data)[:12]}"
