"""Test fixtures. Fakes stand in for the network here so the unit suite runs
without Postgres, a model key, or the detector ML models; end-to-end coverage
against the real stack is the docker-compose smoke test (see Makefile `smoke`)."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from controlplane_decision import DecisionEngine
from controlplane_detectors import DetectionResult, DetectorContext, Severity
from controlplane_policy import PolicyEngine, PolicyRepo
from fastapi.testclient import TestClient

from controlplane_gateway.api.deps import (
    get_audit_store,
    get_decision_engine,
    get_detectors,
    get_ledger_store,
    get_policy_engine,
    get_provider,
)
from controlplane_gateway.main import create_app
from controlplane_gateway.schemas.openai import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)

_POLICIES_DIR = Path(__file__).resolve().parents[2] / "policies"


class FakeProvider:
    name = "fake"
    default_model = "fake-model"

    def __init__(self, content: str = "hello from the fake model") -> None:
        self.calls: list[ChatCompletionRequest] = []
        self.content = content

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        self.calls.append(request)
        return ChatCompletionResponse(
            id="upstream-id",
            created=int(time.time()),
            model=request.model or "fake-model",
            choices=[
                ChatChoice(
                    message=ChatMessage(role="assistant", content=self.content),
                    finish_reason="stop",
                )
            ],
        )

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        pass


class FakeDetector:
    """A detector whose verdict is fixed by the test. ``result_factory`` receives
    the analysed text so a test can key the outcome off the model's answer."""

    def __init__(self, check: str, name: str | None = None, *, result_factory=None, raises=None):
        self.check = check
        self.name = name or f"{check}.fake"
        self._result_factory = result_factory
        self._raises = raises
        self.seen: list[str] = []

    async def analyze(self, text: str, context: DetectorContext) -> DetectionResult:
        self.seen.append(text)
        if self._raises is not None:
            raise self._raises
        if self._result_factory is not None:
            return self._result_factory(text)
        return DetectionResult(detector=self.name, ok=True, severity=Severity.NONE, confidence=0.9)


class FakeAuditStore:
    def __init__(self) -> None:
        self.records: list = []

    async def write(self, record) -> None:
        self.records.append(record)

    async def write_action(self, record) -> None:
        self.records.append(record)

    async def get_by_request_id(self, request_id: str):
        for r in self.records:
            if getattr(r, "request_id", None) == request_id:
                return r
        return None

    async def ping(self) -> bool:
        return True


class FakeLedgerStore:
    def __init__(self) -> None:
        from controlplane_gateway.ledger.models import LedgerState

        self.store: dict[str, LedgerState] = {}

    async def get(self, conversation_id: str):
        from controlplane_gateway.ledger.models import LedgerState

        return self.store.get(conversation_id) or LedgerState(conversation_id=conversation_id)

    async def save(self, state):
        self.store[state.conversation_id] = state


class FakeMailtrapClient:
    def __init__(self, should_raise=False):
        self.calls = []
        self.should_raise = should_raise

    async def send_email(self, to: str, subject: str, body: str) -> dict:
        self.calls.append({"to": to, "subject": subject, "body": body})
        from controlplane_gateway.actions.mailtrap import ActionExecutionError

        if self.should_raise:
            raise ActionExecutionError("Network error injected by test")
        return {"success": True, "message_ids": ["test-id"]}

    async def aclose(self):
        pass


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def fake_audit_store() -> FakeAuditStore:
    return FakeAuditStore()


@pytest.fixture
def detectors() -> list:
    """Default: two clean detectors covering the checks base policy enables."""
    return [FakeDetector("pii"), FakeDetector("toxicity"), FakeDetector("groundedness")]


@pytest.fixture(scope="session")
def policy_engine() -> PolicyEngine:
    # The policy engine is pure and cheap — use the real one over the shipped packs.
    return PolicyEngine(PolicyRepo.from_dir(_POLICIES_DIR))


def _build_client(provider, audit, detectors, policy_engine, ledger_store=None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_audit_store] = lambda: audit
    app.dependency_overrides[get_policy_engine] = lambda: policy_engine
    app.dependency_overrides[get_detectors] = lambda: detectors
    app.dependency_overrides[get_decision_engine] = lambda: DecisionEngine()
    app.dependency_overrides[get_ledger_store] = lambda: ledger_store or FakeLedgerStore()

    # We also need to supply app.state.redis since chat.py needs request.app.state.redis
    # to init the CachedJudgeDetector
    class FakeRedis:
        async def ping(self):
            return True

    app.state.redis = FakeRedis()
    app.state.mailtrap_client = FakeMailtrapClient()

    # No `with` block -> lifespan (real DB/provider/model wiring) does not run.
    return TestClient(app)


@pytest.fixture
def client(
    fake_provider: FakeProvider,
    fake_audit_store: FakeAuditStore,
    detectors: list,
    policy_engine: PolicyEngine,
) -> TestClient:
    return _build_client(fake_provider, fake_audit_store, detectors, policy_engine)


@pytest.fixture
def make_client(policy_engine: PolicyEngine):
    """Build a client with custom fakes. Returns the client; its ``.fakes``
    namespace exposes the provider / detectors / audit store the test wired in."""

    def _make(*, provider=None, detectors=None, audit=None, ledger=None) -> TestClient:
        provider = provider or FakeProvider()
        audit = audit or FakeAuditStore()
        ledger = ledger or FakeLedgerStore()
        if detectors is None:
            detectors = [
                FakeDetector("pii"),
                FakeDetector("toxicity"),
                FakeDetector("groundedness"),
            ]
        client = _build_client(provider, audit, detectors, policy_engine, ledger_store=ledger)
        client.fakes = SimpleNamespace(
            provider=provider, detectors=detectors, audit=audit, ledger=ledger
        )
        return client

    return _make
