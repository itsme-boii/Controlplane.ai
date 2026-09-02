import pytest
from httpx import ASGITransport, AsyncClient
from datetime import datetime, timezone

from controlplane_gateway.audit.models import AuditRecord, Base, ReviewRecord
from controlplane_gateway.audit.store import AuditStore
from controlplane_gateway.main import app


@pytest.fixture
async def audit_store():
    # In-memory SQLite — fast, no Postgres needed for this unit suite.
    store = AuditStore("sqlite+aiosqlite:///:memory:")
    async with store._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield store
    await store.aclose()


@pytest.fixture
async def seeded_audit_store(audit_store):
    record1 = AuditRecord(
        request_id="req_1",
        created_at=datetime.now(timezone.utc),
        policy_version="v1",
        request_body={},
        decision="review",
        usecase_id="default"
    )
    record2 = AuditRecord(
        request_id="req_2",
        created_at=datetime.now(timezone.utc),
        policy_version="v1",
        request_body={},
        decision="allow",
        usecase_id="default"
    )
    await audit_store.write(record1)
    await audit_store.write(record2)
    return audit_store

@pytest.mark.asyncio
async def test_list_records(seeded_audit_store):
    # App state injection is usually done in conftest or setup, but we use the router directly
    # For testing, we might need to patch the dependency
    from controlplane_gateway.api.deps import get_audit_store
    app.dependency_overrides[get_audit_store] = lambda: seeded_audit_store
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/audit/records")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Test filtering by tier
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/audit/records?tier=review")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["request_id"] == "req_1"

@pytest.mark.asyncio
async def test_get_record(seeded_audit_store):
    from controlplane_gateway.api.deps import get_audit_store
    app.dependency_overrides[get_audit_store] = lambda: seeded_audit_store
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/audit/records/req_1")
    assert response.status_code == 200
    data = response.json()
    assert data["record"]["request_id"] == "req_1"
    assert len(data["reviews"]) == 0

@pytest.mark.asyncio
async def test_create_review(seeded_audit_store):
    from controlplane_gateway.api.deps import get_audit_store
    app.dependency_overrides[get_audit_store] = lambda: seeded_audit_store
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/v1/audit/records/req_1/review", json={
            "action": "approve",
            "notes": "Looks good",
            "reviewer_id": "test_user"
        })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    
    # Verify it was added
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        get_response = await ac.get("/v1/audit/records/req_1")
    assert get_response.status_code == 200
    get_data = get_response.json()
    assert len(get_data["reviews"]) == 1
    assert get_data["reviews"][0]["action"] == "approve"
    assert get_data["reviews"][0]["reviewer_id"] == "test_user"
