"""Redis cache wrapping the JudgeDetector.

The judge is a blocking, per-request LLM call. This cache is a latency and cost
optimization. Its failure must not affect the decision path at all (transparent).
"""

from __future__ import annotations

import logging
from typing import Any

from controlplane_detectors import DetectionResult, Detector, DetectorContext
from controlplane_policy.hashing import content_hash

log = logging.getLogger(__name__)


class CachedJudgeDetector(Detector):
    name = "judge.llm_rubric"  # Same name so audit trail is transparent
    check = "judge"

    def __init__(self, inner: Detector, redis: Any, policy_version: str, ttl_s: int) -> None:
        self._inner = inner
        self._redis = redis
        self._policy_version = policy_version
        self._ttl_s = ttl_s

    async def analyze(self, text: str, context: DetectorContext) -> DetectionResult:
        payload = {
            "prompt": context.prompt,
            "text": text,
            "source_documents": context.source_documents,
        }
        key_hash = content_hash(payload)
        key = f"cp:judge:{self._policy_version}:{key_hash}"

        # 1. Try cache read
        try:
            cached_json = await self._redis.get(key)
            if cached_json:
                return DetectionResult.model_validate_json(cached_json)
        except Exception as exc:
            log.warning("Judge cache read failed: %r. Falling back to real detector.", exc)

        # 2. Compute via inner detector
        result = await self._inner.analyze(text, context)

        # 3. Best-effort cache set
        try:
            if result.ok:
                await self._redis.setex(key, self._ttl_s, result.model_dump_json())
        except Exception as exc:
            log.warning("Judge cache write failed: %r", exc)

        return result
