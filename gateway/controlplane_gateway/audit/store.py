"""Async audit store backed by Postgres.

Phase 1 keeps schema management simple (``create_all`` on startup). Phase 7
replaces this with managed migrations when the schema becomes load-bearing.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from controlplane_gateway.audit.chain import compute_hash
from controlplane_gateway.audit.models import (
    ActionRecord,
    AuditRecord,
    Base,
    EvalRunRecord,
    RetentionLogRecord,
    ReviewRecord,
)


class AuditStore:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self._session = async_sessionmaker(self._engine, expire_on_commit=False)
        # Per-table asyncio locks, in addition to the DB-level `FOR UPDATE`
        # below. `FOR UPDATE` is what serializes writers *across processes*
        # against Postgres; it does not reliably serialize concurrent
        # writers *within this one process* against every backend (SQLite,
        # used by the fast test suite, does not enforce row-level locks the
        # way Postgres does). Both are needed for the chain to stay a single
        # linear sequence under real concurrency.
        self._audit_lock = asyncio.Lock()
        self._action_lock = asyncio.Lock()
        self._retention_log_lock = asyncio.Lock()
        self._review_lock = asyncio.Lock()

    async def init_schema(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def write(self, record: AuditRecord) -> None:
        """Persist one interaction. A failure here must not be hidden — it
        propagates so the caller can surface it rather than returning a
        response that was never recorded.

        Phase 7: Each table is chained independently to avoid global lock contention.
        We serialize writes per-table via FOR UPDATE on the latest row (plus an
        in-process lock — see __init__).
        """
        async with self._audit_lock, self._session() as session, session.begin():
            prev = (
                await session.execute(
                    select(AuditRecord.record_hash)
                    .order_by(AuditRecord.id.desc())
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            record.prev_hash = prev
            session.add(record)
            # Flush before hashing: some columns (e.g. `status`) rely on a
            # Python-side `default=`, which SQLAlchemy only resolves at
            # flush/INSERT time — hashing beforehand would chain a value
            # (e.g. status=None) that is never actually what gets persisted,
            # and the verifier would then report every row as tampered.
            await session.flush()
            record.record_hash = compute_hash(prev, record)

        # Broadcast after commit
        from controlplane_gateway.api.audit_api import broadcast_record
        broadcast_record({
            "request_id": record.request_id,
            "created_at": record.created_at.isoformat() if hasattr(record.created_at, "isoformat") else record.created_at,
            "decision": record.decision,
            "usecase_id": record.usecase_id,
        })

    async def write_action(self, record: ActionRecord) -> None:
        async with self._action_lock, self._session() as session, session.begin():
            prev = (
                await session.execute(
                    select(ActionRecord.record_hash)
                    .order_by(ActionRecord.id.desc())
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            record.prev_hash = prev
            session.add(record)
            # See write(): flush first so Python-side defaults (e.g.
            # `executed`) are resolved before they're hashed.
            await session.flush()
            record.record_hash = compute_hash(prev, record)

    async def write_retention_log(self, record: RetentionLogRecord) -> None:
        async with self._retention_log_lock, self._session() as session, session.begin():
            prev = (
                await session.execute(
                    select(RetentionLogRecord.record_hash)
                    .order_by(RetentionLogRecord.id.desc())
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            record.prev_hash = prev
            session.add(record)
            await session.flush()
            record.record_hash = compute_hash(prev, record)

    async def write_review(self, record: ReviewRecord) -> None:
        async with self._review_lock, self._session() as session, session.begin():
            prev = (
                await session.execute(
                    select(ReviewRecord.record_hash)
                    .order_by(ReviewRecord.id.desc())
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            record.prev_hash = prev
            session.add(record)
            await session.flush()
            record.record_hash = compute_hash(prev, record)

    async def write_eval_run(self, record: EvalRunRecord) -> None:
        async with self._session() as session, session.begin():
            session.add(record)

    async def get_by_request_id(self, request_id: str) -> AuditRecord | None:
        async with self._session() as session:
            result = await session.execute(
                select(AuditRecord).where(AuditRecord.request_id == request_id)
            )
            return result.scalar_one_or_none()

    async def ping(self) -> bool:
        async with self._engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return True

    async def aclose(self) -> None:
        await self._engine.dispose()
