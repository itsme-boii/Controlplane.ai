from datetime import UTC, datetime, timedelta

import pytest

from controlplane_gateway.audit.models import ActionRecord, AuditRecord, Base
from controlplane_gateway.audit.retention import run_retention_sweep
from controlplane_gateway.audit.store import AuditStore
from controlplane_gateway.audit.verify import verify_chain


@pytest.fixture
async def audit_store():
    store = AuditStore("sqlite+aiosqlite:///:memory:")
    async with store._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield store
    await store.aclose()


@pytest.mark.asyncio
async def test_retention_sweep_no_op(audit_store):
    now = datetime.now(UTC)
    record = AuditRecord(
        request_id="req_1",
        created_at=now,
        policy_version="v1",
        policy_snapshot={"retention_days": 10},
        request_body={},
        decision="allow",
        decision_detail={},
        gateway_latency_ms=10.0,
        upstream_latency_ms=50.0,
    )
    await audit_store.write(record)

    report = await run_retention_sweep(audit_store, now=now)
    assert report.scanned == 1
    assert report.anonymized == 0

    # Ensure chain is intact
    async with audit_store._session() as session:
        count = await verify_chain(session, AuditRecord, "audit_records")
        assert count == 1


@pytest.mark.asyncio
async def test_retention_sweep_anonymize(audit_store):
    now = datetime.now(UTC)
    past = now - timedelta(days=15)

    # AuditRecord that should be swept
    record = AuditRecord(
        request_id="req_1",
        created_at=past,
        policy_version="v1",
        policy_snapshot={"retention_days": 10},
        decision="allow",
        decision_detail={},
        request_body={"prompt": "test"},
        gateway_latency_ms=10.0,
        upstream_latency_ms=50.0,
    )
    await audit_store.write(record)

    # ActionRecord that should be swept
    action_rec = ActionRecord(
        action_id="act_1",
        request_id="req_1",
        conversation_id=None,
        created_at=past,
        action_type="send_email",
        payload={"to": "test@test.com"},
        action_decision="allow",
        reason="",
        executed=False,
    )
    await audit_store.write_action(action_rec)

    report = await run_retention_sweep(audit_store, now=now)
    assert report.scanned == 2
    assert report.anonymized == 2

    async with audit_store._session() as session:
        # Check AuditRecord is anonymized
        audit_db = await audit_store.get_by_request_id("req_1")
        assert audit_db.anonymized is True
        assert audit_db.request_body["redacted"] is True

        # Check ActionRecord is anonymized
        action_db = await session.get(ActionRecord, 1)
        assert action_db.anonymized is True
        assert action_db.payload["redacted"] is True

        # We can just verify the chain
        count_audit = await verify_chain(session, AuditRecord, "audit_records")
        assert count_audit == 1

        count_action = await verify_chain(session, ActionRecord, "action_records")
        assert count_action == 1

        # Idempotency: Run again
        report2 = await run_retention_sweep(audit_store, now=now)
        # Should not scan anything since we filter by anonymized == False
        assert report2.scanned == 0
        assert report2.anonymized == 0
