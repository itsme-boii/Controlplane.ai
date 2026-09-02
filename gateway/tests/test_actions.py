from __future__ import annotations

from datetime import UTC, datetime

from controlplane_decision import Decision
from controlplane_policy import EffectivePolicy, Tier

from controlplane_gateway.audit.models import AuditRecord
from controlplane_gateway.ledger.models import LedgerState


def _build_audit_record(request_id: str, tier: Tier, confidence: float) -> AuditRecord:
    policy = EffectivePolicy.model_validate(
        {
            "meta": {"name": "base", "kind": "base", "effective_from": "2026-01-01"},
            "latency_path": "deep",
            "latency_budget_ms": 1500,
            "confidence_floor": 0.5,
            "checks": {},
            "pii": {"action": "edit", "entities": []},
            "decision_rules": [],
            "retention_days": 365,
            "action_policy": {
                "enabled": True,
                "actions": {
                    "send_email": {
                        "min_confidence": 0.8,
                        "max_text_tier": "allow",
                        "block_if_ledger_escalated": True,
                    }
                },
            },
        }
    )

    decision = Decision(
        tier=tier,
        rule_index=None,
        rule_note="fallback",
        confidence=confidence,
        assessment={"confidence": confidence, "risks": {}, "failed_detectors": []},
        reasons=[],
    )

    return AuditRecord(
        request_id=request_id,
        created_at=datetime.now(UTC),
        policy_version="base:v1",
        policy_snapshot=policy.model_dump(mode="json"),
        request_body={},
        response_body={},
        decision=tier.value,
        decision_detail=decision.model_dump(mode="json"),
        gateway_latency_ms=10,
        upstream_latency_ms=100,
    )


def test_action_allowed(client, fake_audit_store):
    record = _build_audit_record("req1", Tier.ALLOW, 0.9)
    fake_audit_store.records.append(record)

    resp = client.post(
        "/v1/actions/execute",
        json={
            "request_id": "req1",
            "action_type": "send_email",
            "payload": {"to": "user@test.com", "subject": "Hello", "body": "World"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_decision"] == "allow"
    assert data["executed"] is True

    assert len(client.app.state.mailtrap_client.calls) == 1
    call = client.app.state.mailtrap_client.calls[0]
    assert call["to"] == "user@test.com"


def test_action_blocked_by_text_tier(client, fake_audit_store):
    record = _build_audit_record("req2", Tier.REVIEW, 0.9)
    fake_audit_store.records.append(record)

    resp = client.post(
        "/v1/actions/execute",
        json={"request_id": "req2", "action_type": "send_email", "payload": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_decision"] == "block"
    assert data["executed"] is False
    assert len(client.app.state.mailtrap_client.calls) == 0


def test_action_blocked_by_low_confidence(client, fake_audit_store):
    # Action requires 0.8, text got 0.7
    record = _build_audit_record("req3", Tier.ALLOW, 0.7)
    fake_audit_store.records.append(record)

    resp = client.post(
        "/v1/actions/execute",
        json={"request_id": "req3", "action_type": "send_email", "payload": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_decision"] == "review"
    assert data["executed"] is False
    assert len(client.app.state.mailtrap_client.calls) == 0


def test_action_blocked_by_ledger_escalated(make_client):
    client = make_client()
    record = _build_audit_record("req4", Tier.ALLOW, 0.9)
    client.fakes.audit.records.append(record)

    # Pre-populate ledger with escalated state
    escalated_state = LedgerState(
        conversation_id="conv1",
        escalated=True,
        escalated_at_turn=1,
        escalated_reason="test",
        residual_risk={},
        turns=[],
    )

    client.fakes.ledger.store["conv1"] = escalated_state

    resp = client.post(
        "/v1/actions/execute",
        json={
            "request_id": "req4",
            "conversation_id": "conv1",
            "action_type": "send_email",
            "payload": {},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_decision"] == "block"
    assert data["executed"] is False
    assert "escalated" in data["reason"]


def test_action_unknown_request_id(client):
    resp = client.post(
        "/v1/actions/execute",
        json={"request_id": "nope", "action_type": "send_email", "payload": {}},
    )
    assert resp.status_code == 404


def test_action_execution_error(client, fake_audit_store):
    client.app.state.mailtrap_client.should_raise = True
    record = _build_audit_record("req5", Tier.ALLOW, 0.9)
    fake_audit_store.records.append(record)

    resp = client.post(
        "/v1/actions/execute",
        json={"request_id": "req5", "action_type": "send_email", "payload": {}},
    )
    assert resp.status_code == 502
    data = resp.json()
    assert data["action_decision"] == "allow"
    assert data["executed"] is False
    assert "Action execution failed" in data["reason"]
