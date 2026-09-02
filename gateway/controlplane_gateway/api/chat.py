"""OpenAI-compatible chat-completions endpoint.

Per request: resolve the effective policy, forward to the model, run the policy's
enabled detectors over the model's answer, and turn their findings into a tiered
decision (allow / edit / review / block). The decision is enforced before the
response leaves the gateway:

* **allow**  — response returned unchanged.
* **edit**   — PII spans masked in place, then returned.
* **review** — response withheld; ``409`` with the request id so a human can
  pull it from the audit trail.
* **block**  — response withheld; ``403``.

An audit record is written on *every* path, including upstream failures and
withheld responses — the full model output and the evidence are always stored
even when the caller does not receive them. Nothing is ever faked: an upstream
failure is a ``502``, a detector that cannot run routes the request to review.
"""

from __future__ import annotations

import asyncio
import time
import uuid

from controlplane_detectors import DetectionResult, Detector, DetectorContext
from controlplane_policy import EffectivePolicy, PolicyResolutionError, Tier
from fastapi import APIRouter, Header, HTTPException, Request, Response

from controlplane_gateway.api.deps import (
    AuditStoreDep,
    DecisionEngineDep,
    DetectorsDep,
    LedgerStoreDep,
    PolicyEngineDep,
    ProviderDep,
)
from controlplane_gateway.audit import AuditRecord
from controlplane_gateway.config import get_settings
from controlplane_gateway.judge_cache import CachedJudgeDetector
from controlplane_gateway.ledger import accumulate, score_turn
from controlplane_gateway.models import ProviderError
from controlplane_gateway.schemas.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)

router = APIRouter(prefix="/v1", tags=["chat"])


async def _run_detector(detector: Detector, text: str, context: DetectorContext) -> DetectionResult:
    """Detectors already convert their own failures to ``ok=False``; this is the
    outer guard for anything that still escapes, so one broken detector routes to
    review instead of 500-ing the request."""
    try:
        return await detector.analyze(text, context)
    except Exception as exc:  # noqa: BLE001 — missing evidence, surfaced not hidden
        return DetectionResult.failed(detector.name, f"detector raised: {exc!r}")


async def _analyse(
    text: str,
    context: DetectorContext,
    detectors: list[Detector],
    policy: EffectivePolicy,
) -> list[DetectionResult]:
    enabled = set(policy.enabled_checks())
    active = [d for d in detectors if getattr(d, "check", None) in enabled]
    if not text or not active:
        return []
    return list(await asyncio.gather(*(_run_detector(d, text, context) for d in active)))


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    body: ChatCompletionRequest,
    response: Response,
    provider: ProviderDep,
    audit_store: AuditStoreDep,
    policy_engine: PolicyEngineDep,
    detectors: DetectorsDep,
    decision_engine: DecisionEngineDep,
    ledger_store: LedgerStoreDep,
    request: Request,
    x_usecase_id: str | None = Header(default=None),
    x_jurisdiction: str | None = Header(default=None),
    x_conversation_id: str | None = Header(default=None),
) -> ChatCompletionResponse:
    if body.stream:
        # Streaming (buffer-and-release) is a later-phase decision; reject
        # explicitly rather than silently returning a non-streamed body.
        raise HTTPException(status_code=501, detail="streaming is not supported yet")

    try:
        policy = policy_engine.resolve(x_usecase_id, x_jurisdiction)
    except PolicyResolutionError as exc:
        # Bad use-case / jurisdiction header — a client error, and nothing is
        # forwarded to the model without a resolved policy.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request_id = f"cp_{uuid.uuid4().hex}"
    started = time.perf_counter()

    record = AuditRecord(
        request_id=request_id,
        usecase_id=x_usecase_id,
        jurisdiction=x_jurisdiction,
        policy_version=policy.version,
        policy_snapshot=policy.model_dump(mode="json"),
        model=body.model or provider.default_model,
        request_body=body.model_dump(mode="json", exclude_none=True),
    )

    try:
        upstream_start = time.perf_counter()
        upstream = await provider.chat_completion(body)
        record.upstream_latency_ms = (time.perf_counter() - upstream_start) * 1000
        record.response_body = upstream.model_dump(mode="json")
        record.status = "ok"
    except ProviderError as exc:
        record.status = "error"
        record.error = str(exc)
        record.gateway_latency_ms = (time.perf_counter() - started) * 1000
        await audit_store.write(record)
        # Real failure surfaced as 502 — never a fabricated completion.
        raise HTTPException(status_code=502, detail=f"upstream model error: {exc}") from exc

    answer = upstream.first_text()
    context = DetectorContext(
        usecase_id=x_usecase_id,
        jurisdiction=x_jurisdiction,
        prompt=body.last_user_text(),
        source_documents=body.source_documents or [],
    )

    settings = get_settings()

    # Wrap judge detector with cache if present
    effective_detectors = []
    for d in detectors:
        if d.name == "judge.llm_rubric":
            effective_detectors.append(
                CachedJudgeDetector(
                    inner=d,
                    redis=request.app.state.redis,
                    policy_version=policy.version,
                    ttl_s=settings.judge_cache_ttl_s,
                )
            )
        else:
            effective_detectors.append(d)

    results = await _analyse(answer, context, effective_detectors, policy)
    decision = decision_engine.decide(answer, results, policy)

    # Ledger integration
    ledger_state = None
    if x_conversation_id and settings.ledger_enabled:
        try:
            ledger_state = await ledger_store.get(x_conversation_id)
            turn_scores = score_turn(decision.assessment)
            ledger_state = accumulate(
                ledger_state,
                turn_scores,
                request_id=request_id,
                tier=decision.tier,
                confidence=decision.confidence,
            )
            await ledger_store.save(ledger_state)
        except Exception as exc:
            if decision.tier in (Tier.ALLOW, Tier.EDIT):
                decision.tier = Tier.REVIEW
                decision.fail_safe_triggered = True
                decision.reasons.append(
                    f"conversation ledger unavailable: {exc!r}; "
                    "missing accumulated-risk evidence never allows"
                )
            ledger_state = None
        else:
            if ledger_state.escalated and decision.tier in (Tier.ALLOW, Tier.EDIT):
                decision.tier = Tier.REVIEW
                decision.fail_safe_triggered = True
                decision.reasons.append(
                    f"conversation escalated at turn {ledger_state.escalated_at_turn}: "
                    f"{ledger_state.escalated_reason}"
                )

    record.decision = decision.tier.value
    record.detector_results = [r.model_dump(mode="json") for r in results]
    record.decision_detail = decision.model_dump(mode="json")
    record.gateway_latency_ms = (time.perf_counter() - started) * 1000

    cp_headers = {
        "X-ControlPlane-Request-Id": request_id,
        "X-ControlPlane-Decision": decision.tier.value,
        "X-ControlPlane-Policy-Version": policy.version,
    }
    if x_conversation_id:
        cp_headers["X-ControlPlane-Conversation-Id"] = x_conversation_id
        is_escalated = "true" if (ledger_state and ledger_state.escalated) else "false"
        cp_headers["X-ControlPlane-Ledger-Escalated"] = is_escalated

    if not decision.released_text_allowed:
        # review / block: persist everything, hand back only a pointer.
        await audit_store.write(record)
        status_code = 403 if decision.tier.value == "block" else 409
        raise HTTPException(
            status_code=status_code,
            detail={
                "decision": decision.tier.value,
                "request_id": request_id,
                "categories": sorted(c.value for c in decision.assessment.categories),
                "rationale": decision.rationale,
            },
            headers=cp_headers,
        )

    await audit_store.write(record)

    if decision.tier.value == "edit" and decision.redaction is not None:
        upstream.choices[0].message.content = decision.redaction.text

    # The full response (reasoning trace included) is in the audit record; the
    # caller gets only the governed `content`.
    upstream.drop_reasoning()
    upstream.id = request_id  # let callers correlate the response with the audit trail
    response.headers.update(cp_headers)
    return upstream
