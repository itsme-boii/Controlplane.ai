#!/usr/bin/env python3
"""Runs the eval corpus (evals/corpus/*.jsonl) against the REAL, live gateway
and records genuine precision/recall/F1 from the actual tiered decisions —
no simulated or randomized results. Requires a running gateway (``docker
compose up``, same as scripts/smoke.sh) reachable at GATEWAY_URL, and a real
model backend behind it (GROQ_API_KEY).

Each corpus line is ``{"prompt": str, "expected_flag": str|null, "expected_tier":
"allow"|"edit"|"review"|"block"}``. The primary metric is binary — "should
this have been let through unchanged, or not" — which is what the Metrics
dashboard's false-positive/false-negative cards actually mean here:
  - false positive: clean content (expected_tier == allow) the gateway
    wrongly withheld or edited.
  - false negative: risky content (expected_tier != allow) the gateway
    wrongly let through unchanged.

An example the gateway can't be reached for, or that returns no
X-ControlPlane-Decision header at all, is a real infrastructure failure —
it is recorded as an error and excluded from the computed rates, never
silently folded into any bucket (no-false-fallback, same rule as everywhere
else in this codebase). If every example errors, nothing is written: an
eval run over zero real answers is not a metric, it's a fabrication.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
TIMEOUT_S = float(os.environ.get("EVAL_TIMEOUT_S", "60"))


def load_corpus(corpus_dir: Path) -> list[dict]:
    examples = []
    for file in sorted(corpus_dir.glob("*.jsonl")):
        with open(file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                row["_source_file"] = file.name
                examples.append(row)
    return examples


async def run_example(client: httpx.AsyncClient, example: dict) -> dict:
    """POST the corpus prompt to the real gateway and read the *actual*
    decision straight off the response headers — present on the withheld
    (403/409) paths too, not just 200, so no need to special-case status
    codes to know what happened."""
    try:
        resp = await client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": example["prompt"]}]},
        )
    except httpx.HTTPError as exc:
        return {**example, "actual_tier": None, "error": f"request failed: {exc!r}"}

    actual_tier = resp.headers.get("x-controlplane-decision")
    request_id = resp.headers.get("x-controlplane-request-id")
    if actual_tier is None:
        # A real infrastructure failure upstream of the decision engine
        # (e.g. the model provider itself 502'd) — missing evidence, not a
        # result we can score.
        return {
            **example,
            "actual_tier": None,
            "request_id": request_id,
            "error": f"no decision header; http {resp.status_code}: {resp.text[:200]}",
        }
    return {**example, "actual_tier": actual_tier, "request_id": request_id, "http_status": resp.status_code}


async def main() -> None:
    root = Path(__file__).parent.parent
    corpus_dir = root / "evals" / "corpus"

    if not corpus_dir.exists():
        print(f"Corpus directory {corpus_dir} not found")
        sys.exit(1)

    examples = load_corpus(corpus_dir)
    if not examples:
        print("No examples found in evals/corpus/*.jsonl")
        sys.exit(1)

    print(f"Running {len(examples)} corpus examples against the real gateway at {GATEWAY_URL} ...")

    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=TIMEOUT_S) as client:
        try:
            await client.get("/readyz")
        except httpx.HTTPError as exc:
            print(f"Gateway at {GATEWAY_URL} is not reachable ({exc!r}). "
                  f"Start it first: docker compose up --build -d")
            sys.exit(1)

        # Sequential, not concurrent: the corpus is small and this avoids
        # surprising rate limits on the real upstream model.
        results = [await run_example(client, ex) for ex in examples]

    errors = [r for r in results if r["actual_tier"] is None]
    scored = [r for r in results if r["actual_tier"] is not None]

    for r in results:
        status = "ERROR" if r["actual_tier"] is None else r["actual_tier"]
        print(f"  [{status:>8}] expected={r['expected_tier']:<7} "
              f"{r['_source_file']}: {r['prompt'][:70]!r}")
        if r["actual_tier"] is None:
            print(f"             -> {r['error']}")

    if not scored:
        print("\nEvery example errored — no real answers to score. Nothing written.")
        sys.exit(1)

    tp = fp = fn = tn = 0
    exact_tier_matches = 0
    for r in scored:
        expected_positive = r["expected_tier"] != "allow"
        actual_positive = r["actual_tier"] != "allow"
        if r["actual_tier"] == r["expected_tier"]:
            exact_tier_matches += 1
        if expected_positive and actual_positive:
            tp += 1
        elif not expected_positive and actual_positive:
            fp += 1
        elif expected_positive and not actual_positive:
            fn += 1
        else:
            tn += 1

    total = len(scored)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fp_rate = fp / total
    fn_rate = fn / total

    print(f"\nScored {total}/{len(examples)} examples ({len(errors)} errored, excluded from rates)")
    print(f"Exact tier match: {exact_tier_matches}/{total}")
    print(f"TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"Precision: {precision:.2f}, Recall: {recall:.2f}, F1: {f1:.2f}, "
          f"FP rate: {fp_rate:.2f}, FN rate: {fn_rate:.2f}")

    sys.path.insert(0, str(root / "gateway"))
    from controlplane_gateway.audit.models import EvalRunRecord
    from controlplane_gateway.audit.store import AuditStore
    from controlplane_gateway.config import get_settings

    settings = get_settings()
    audit_store = AuditStore(settings.database_url)

    record = EvalRunRecord(
        run_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        total_examples=total,
        precision=precision,
        recall=recall,
        f1_score=f1,
        fp_rate=fp_rate,
        fn_rate=fn_rate,
        metrics_detail={
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
            "exact_tier_matches": exact_tier_matches,
            "errored_examples": len(errors),
            "results": [
                {k: v for k, v in r.items() if k != "_source_file"} for r in results
            ],
        },
    )

    await audit_store.write_eval_run(record)
    await audit_store.aclose()
    print(f"\nEval run {record.run_id} recorded to the audit store.")


if __name__ == "__main__":
    asyncio.run(main())
