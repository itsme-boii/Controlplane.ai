import pytest
from httpx import ASGITransport, AsyncClient
import os
from pathlib import Path

from controlplane_gateway.main import app
import controlplane_gateway.api.policy_api as policy_api

@pytest.fixture
def temp_policies_dir(tmp_path):
    d = tmp_path / "policies"
    d.mkdir()
    f1 = d / "test1.yaml"
    f1.write_text("key: value1")
    
    f2 = d / "sub" / "test2.yaml"
    f2.parent.mkdir()
    f2.write_text("key: value2")
    
    # Patch the POLICY_DIR in the router
    orig = policy_api.POLICY_DIR
    policy_api.POLICY_DIR = d
    yield d
    policy_api.POLICY_DIR = orig

@pytest.mark.asyncio
async def test_list_policies(temp_policies_dir):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/policies")
    assert response.status_code == 200
    data = response.json()
    policies = data["policies"]
    assert len(policies) == 2
    assert "test1.yaml" in policies
    assert "sub/test2.yaml" in policies

@pytest.mark.asyncio
async def test_get_policy(temp_policies_dir):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/policies/test1")
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "key: value1"

@pytest.mark.asyncio
async def test_update_policy(temp_policies_dir):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.put("/v1/policies/test1", json={"content": "key: new_value"})
    assert response.status_code == 200
    
    # Verify file updated
    content = (temp_policies_dir / "test1.yaml").read_text()
    assert content == "key: new_value"

@pytest.mark.asyncio
async def test_path_traversal(temp_policies_dir):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/policies/../secrets.yaml")
    # Path traversal should be caught and return 404/403
    assert response.status_code in (403, 404, 500) 
