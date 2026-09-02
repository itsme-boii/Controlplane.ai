"""Phase 1: the gateway forwards the call, returns it unchanged, and audits it."""

from __future__ import annotations

from controlplane_gateway.api.deps import get_provider
from controlplane_gateway.models import ProviderError


def test_passthrough_returns_model_response_and_audits(client, fake_provider, fake_audit_store):
    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Usecase-Id": "SupportAssist", "X-Jurisdiction": "US"},
        json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "hello from the fake model"
    assert body["id"].startswith("cp_")  # response id correlates with the audit record

    assert len(fake_provider.calls) == 1
    assert len(fake_audit_store.records) == 1
    rec = fake_audit_store.records[0]
    assert rec.status == "ok"
    assert rec.decision == "allow"
    assert rec.usecase_id == "SupportAssist"
    assert rec.jurisdiction == "US"
    assert rec.request_id == body["id"]
    assert rec.response_body is not None
    assert rec.gateway_latency_ms is not None
    # Phase 2: a real, content-hashed policy version is recorded with a snapshot.
    assert rec.policy_version.startswith("supportassist+us:")
    assert rec.policy_snapshot["latency_path"] == "fast"


def test_unknown_usecase_header_is_a_400_and_not_forwarded(client, fake_provider, fake_audit_store):
    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Usecase-Id": "NoSuchApp"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 400
    assert fake_provider.calls == []
    assert fake_audit_store.records == []


def test_no_headers_resolves_base_policy(client, fake_audit_store):
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    assert fake_audit_store.records[0].policy_version.startswith("base:")


def test_streaming_is_rejected_not_faked(client):
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
    )
    assert resp.status_code == 501


def test_upstream_error_surfaces_as_502_and_is_audited(client, fake_audit_store):
    class BrokenProvider:
        name = "broken"
        default_model = "broken-model"

        async def chat_completion(self, request):
            raise ProviderError("model is down")

        async def aclose(self):
            pass

    client.app.dependency_overrides[get_provider] = lambda: BrokenProvider()

    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert resp.status_code == 502
    assert len(fake_audit_store.records) == 1
    assert fake_audit_store.records[0].status == "error"
    assert "model is down" in fake_audit_store.records[0].error
