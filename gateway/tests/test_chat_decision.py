"""Phase 4: the gateway runs detectors over the model's answer and enforces the
tiered decision before responding. The fail-safe cases here are the HTTP-level
half of the no-false-fallback exit gate (the engine-level half is in
``decision/tests/test_failsafe.py``)."""

from __future__ import annotations

import pytest
from conftest import FakeDetector, FakeProvider
from controlplane_detectors import Category, DetectionResult, Severity, Span

_BODY = {"messages": [{"role": "user", "content": "tell me something"}]}


def _post(client, body=None, headers=None):
    return client.post("/v1/chat/completions", json=body or _BODY, headers=headers or {})


def _finding(detector: str, category: Category, severity: Severity, **kw) -> DetectionResult:
    return DetectionResult(
        detector=detector, ok=True, categories=[category], severity=severity, confidence=0.95, **kw
    )


def test_clean_answer_is_allowed_and_annotated(client, fake_audit_store):
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.headers["X-ControlPlane-Decision"] == "allow"
    assert resp.headers["X-ControlPlane-Request-Id"] == resp.json()["id"]
    rec = fake_audit_store.records[0]
    assert rec.decision == "allow"
    assert rec.decision_detail["fail_safe_triggered"] is False
    assert isinstance(rec.detector_results, list)


def test_pii_in_the_answer_is_masked_in_place(make_client):
    answer = "Sure — email her at jane@acme.com."

    def pii_result(text: str) -> DetectionResult:
        start = text.index("jane@acme.com")
        return _finding(
            "pii.presidio",
            Category.PII,
            Severity.MEDIUM,
            spans=[Span(start=start, end=start + 13, text="jane@acme.com", label="EMAIL_ADDRESS")],
        )

    client = make_client(
        provider=FakeProvider(content=answer),
        detectors=[FakeDetector("pii", "pii.presidio", result_factory=pii_result)],
    )
    resp = _post(client)

    assert resp.status_code == 200
    assert resp.headers["X-ControlPlane-Decision"] == "edit"
    assert "jane@acme.com" not in resp.json()["choices"][0]["message"]["content"]
    # the unredacted original is still in the audit trail
    stored = client.fakes.audit.records[0].response_body["choices"][0]["message"]["content"]
    assert "jane@acme.com" in stored


def test_high_severity_finding_blocks_and_withholds_the_answer(client, fake_audit_store, detectors):
    detectors[1] = FakeDetector(
        "toxicity",
        "toxicity_bias.fake",
        result_factory=lambda _t: _finding("toxicity_bias.fake", Category.TOXICITY, Severity.HIGH),
    )
    resp = _post(client)
    assert resp.status_code == 403
    body = resp.json()["detail"]
    assert body["decision"] == "block"
    assert "toxicity" in body["categories"]
    assert body["request_id"] == resp.headers["X-ControlPlane-Request-Id"]
    # persisted with the full evidence even though the caller got none of it
    rec = fake_audit_store.records[0]
    assert rec.decision == "block"
    assert rec.response_body is not None


def test_detector_failure_routes_to_review_not_allow(client, fake_audit_store, detectors):
    detectors[0] = FakeDetector("pii", "pii.presidio", raises=RuntimeError("presidio OOM"))
    resp = _post(client)
    assert resp.status_code == 409
    assert resp.json()["detail"]["decision"] == "review"
    rec = fake_audit_store.records[0]
    assert rec.decision == "review"
    # the failing detector is recorded as missing evidence, not a clean pass
    failed = [r for r in rec.detector_results if r["ok"] is False]
    assert [r["detector"] for r in failed] == ["pii.presidio"]
    assert "no-false-fallback" in rec.decision_detail["rationale"]


def test_detector_timeout_is_not_a_silent_pass(client, fake_audit_store, detectors):
    detectors[2] = FakeDetector("groundedness", "groundedness.nli", raises=TimeoutError())
    resp = _post(client)
    assert resp.status_code == 409
    assert fake_audit_store.records[0].decision == "review"


def test_reasoning_trace_is_not_forwarded_to_the_caller(make_client):
    provider = FakeProvider()

    async def with_reasoning(request):
        resp = await FakeProvider.chat_completion(provider, request)
        resp.choices[0].message.__pydantic_extra__["reasoning"] = (
            "secret CoT: user is jane@acme.com"
        )
        return resp

    provider.chat_completion = with_reasoning
    client = make_client(provider=provider)
    resp = client.post("/v1/chat/completions", json=_BODY)
    assert resp.status_code == 200
    assert "reasoning" not in resp.json()["choices"][0]["message"]
    assert "jane@acme.com" not in resp.text
    # but the full trace is kept in the audit record
    stored = client.fakes.audit.records[0].response_body["choices"][0]["message"]
    assert stored["reasoning"].startswith("secret CoT")


def test_only_policy_enabled_detectors_run(client, detectors):
    # supportassist disables groundedness; that detector must not be invoked.
    _post(client, headers={"X-Usecase-Id": "SupportAssist"})
    assert detectors[2].seen == []  # groundedness
    assert detectors[0].seen and detectors[1].seen


def test_source_documents_reach_detectors_but_not_the_upstream_model(client, fake_provider):
    _post(client, body={**_BODY, "source_documents": ["The sky is blue."]})
    forwarded = fake_provider.calls[0]
    assert forwarded.source_documents == ["The sky is blue."]
    assert "source_documents" not in forwarded.extra_params()


def test_upstream_failure_short_circuits_before_detectors(client, fake_audit_store, detectors):
    from controlplane_gateway.api.deps import get_provider
    from controlplane_gateway.models import ProviderError

    class Broken:
        name = "broken"
        default_model = "broken-model"

        async def chat_completion(self, request):
            raise ProviderError("model is down")

        async def aclose(self):
            pass

    client.app.dependency_overrides[get_provider] = lambda: Broken()
    resp = _post(client)
    assert resp.status_code == 502
    assert fake_audit_store.records[0].decision is None  # never fabricated
    assert detectors[0].seen == []


@pytest.mark.parametrize("geo", ["US", "EU"])
def test_decision_is_recorded_with_the_resolved_policy_version(client, fake_audit_store, geo):
    _post(client, headers={"X-Usecase-Id": "KnowledgeCopilot", "X-Jurisdiction": geo})
    rec = fake_audit_store.records[0]
    assert rec.policy_version.startswith(f"knowledgecopilot+{geo.lower()}:")
    assert rec.decision_detail["confidence"] == rec.decision_detail["assessment"]["confidence"]
