"""Core detector contract shared across the whole system."""

from __future__ import annotations

import abc
import enum

from pydantic import BaseModel, Field


class Category(enum.StrEnum):
    """Risk categories. A single finding may carry several (multi-label):
    e.g. a fabricated fact about a real person is HALLUCINATION + PRIVACY."""

    PII = "pii"
    PRIVACY = "privacy"
    HALLUCINATION = "hallucination"
    BIAS = "bias"
    TOXICITY = "toxicity"
    INJECTION = "injection"
    POLICY = "policy"  # generic policy-rubric violation (AI-as-judge)


class Severity(enum.StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Span(BaseModel):
    """A character range in the analysed text that triggered a finding."""

    start: int
    end: int
    text: str
    label: str | None = None


class DetectionResult(BaseModel):
    """Uniform output of every detector.

    ``ok`` is False when the detector could not complete (dependency down,
    timeout, error). Per the no-false-fallback rule the decision engine treats
    ``ok is False`` as *missing evidence* and routes to review — never allow.
    """

    detector: str
    ok: bool = True
    categories: list[Category] = Field(default_factory=list)
    severity: Severity = Severity.NONE
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    spans: list[Span] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    rationale: str = ""
    latency_ms: float | None = None

    @classmethod
    def failed(cls, detector: str, reason: str) -> DetectionResult:
        """Construct the result for a detector that could not run."""
        return cls(detector=detector, ok=False, rationale=reason, confidence=0.0)


class DetectorContext(BaseModel):
    """Everything a detector may need beyond the raw text under inspection."""

    usecase_id: str | None = None
    jurisdiction: str | None = None
    prompt: str | None = None
    source_documents: list[str] = Field(default_factory=list)
    logprobs: list[float] | None = None


class Detector(abc.ABC):
    """Base class for all detectors. Concrete detectors arrive in Phase 3+."""

    name: str
    # The policy `checks:` key this detector implements. The gateway runs a
    # detector only when its check is enabled in the effective policy.
    check: str

    @abc.abstractmethod
    async def analyze(self, text: str, context: DetectorContext) -> DetectionResult: ...
