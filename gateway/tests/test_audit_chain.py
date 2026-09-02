import asyncio
from datetime import UTC, datetime

import pytest

from controlplane_gateway.audit.models import ActionRecord, AuditRecord, Base
from controlplane_gateway.audit.store import AuditStore
from controlplane_gateway.audit.verify import verify_chain


@pytest.fixture
async def audit_store():
    # Use an in-memory SQLite database for fast tests
    # We use sqlite for the test since we just need simple concurrent locking semantics if possible.
    # Note: SQLite doesn't truly support FOR UPDATE the way Postgres does, it locks the whole DB.
    # But for the purpose of the test it will serialize correctly.
    store = AuditStore("sqlite+aiosqlite:///:memory:")

    async with store._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield store
    await store.aclose()


@pytest.mark.asyncio
async def test_audit_chain_sequential(audit_store):
    for i in range(5):
        record = AuditRecord(
            request_id=f"req_{i}",
            created_at=datetime.now(UTC),
            policy_version="v1",
            policy_snapshot={"retention_days": 10},
            request_body={},
            decision="allow",
            decision_detail={},
            gateway_latency_ms=10.0,
            upstream_latency_ms=50.0,
        )
        await audit_store.write(record)

    # Verify chain
    async with audit_store._session() as session:
        count = await verify_chain(session, AuditRecord, "audit_records")
        assert count == 5


@pytest.mark.asyncio
async def test_audit_chain_tamper(audit_store):
    record1 = AuditRecord(
        request_id="req_1",
        created_at=datetime.now(UTC),
        policy_version="v1",
        policy_snapshot={"retention_days": 10},
        request_body={},
        decision="allow",
        decision_detail={},
        gateway_latency_ms=10.0,
        upstream_latency_ms=50.0,
    )
    await audit_store.write(record1)

    record2 = AuditRecord(
        request_id="req_2",
        created_at=datetime.now(UTC),
        policy_version="v1",
        policy_snapshot={"retention_days": 10},
        request_body={},
        decision="allow",
        decision_detail={},
        gateway_latency_ms=10.0,
        upstream_latency_ms=50.0,
    )
    await audit_store.write(record2)

    # Tamper with the database
    async with audit_store._session() as session, session.begin():
        rec = await session.get(AuditRecord, 1)
        rec.response_body = {"tampered": True}
        session.add(rec)

    async with audit_store._session() as session:
        with pytest.raises(SystemExit) as exc:
            await verify_chain(session, AuditRecord, "audit_records")
        assert exc.value.code == 1


@pytest.mark.asyncio
async def test_audit_chain_independent(audit_store):
    audit_rec = AuditRecord(
        request_id="req_1",
        created_at=datetime.now(UTC),
        policy_version="v1",
        policy_snapshot={"retention_days": 10},
        request_body={},
        decision="allow",
        decision_detail={},
        gateway_latency_ms=10.0,
        upstream_latency_ms=50.0,
    )
    await audit_store.write(audit_rec)

    action_rec = ActionRecord(
        action_id="act_1",
        request_id="req_1",
        conversation_id=None,
        action_type="send_email",
        payload={},
        action_decision="allow",
        reason="",
        executed=False,
    )
    await audit_store.write_action(action_rec)

    # Tamper with audit
    async with audit_store._session() as session, session.begin():
        rec = await session.get(AuditRecord, 1)
        rec.response_body = {"tampered": True}
        session.add(rec)

    # Action chain should still be valid
    async with audit_store._session() as session:
        count = await verify_chain(session, ActionRecord, "action_records")
        assert count == 1


@pytest.mark.asyncio
async def test_audit_chain_concurrent_writers(audit_store):
    async def writer(i):
        record = AuditRecord(
            request_id=f"req_{i}",
            created_at=datetime.now(UTC),
            policy_version="v1",
            policy_snapshot={"retention_days": 10},
            request_body={},
            decision="allow",
            decision_detail={},
            gateway_latency_ms=10.0,
            upstream_latency_ms=50.0,
        )
        await audit_store.write(record)

    await asyncio.gather(*(writer(i) for i in range(10)))

    # Verify chain
    async with audit_store._session() as session:
        count = await verify_chain(session, AuditRecord, "audit_records")
        assert count == 10
