"""Redis store for conversation risk ledger."""

from __future__ import annotations

import logging
from typing import Any

from controlplane_gateway.ledger.models import LedgerState

log = logging.getLogger(__name__)


class RedisLedgerStore:
    def __init__(self, redis: Any, ttl_s: int) -> None:
        self._redis = redis
        self._ttl_s = ttl_s

    async def get(self, conversation_id: str) -> LedgerState:
        """Fetch the LedgerState. A missing key returns a fresh empty state.
        A real Redis error must propagate so we don't silently lose accumulated risk.
        """
        key = f"cp:ledger:{conversation_id}"
        # Let exceptions propagate (no try-except here) per the no-false-fallback rule
        data = await self._redis.get(key)
        if data:
            return LedgerState.model_validate_json(data)
        return LedgerState(conversation_id=conversation_id)

    async def save(self, state: LedgerState) -> None:
        """Save the LedgerState with TTL. Propagates errors."""
        key = f"cp:ledger:{state.conversation_id}"
        await self._redis.setex(key, self._ttl_s, state.model_dump_json())
