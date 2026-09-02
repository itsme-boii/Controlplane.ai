# Detector library

Every detector implements one contract — `analyze(text, DetectorContext) -> DetectionResult`
— so the decision engine consumes only `DetectionResult` and never imports a
concrete detector.

```python
from controlplane_detectors import default_detectors, warmup, DetectorContext

warmup()  # load models once, at startup
ctx = DetectorContext(source_documents=[...])
results = [await d.analyze(text, ctx) for d in default_detectors()]
```

## Batch 1 (Phase 3)

| Detector | Name | Mechanism | Emits |
| --- | --- | --- | --- |
| PII / privacy | `pii.presidio` | Microsoft Presidio — spaCy `en_core_web_lg` NER + regex + checksum validators (Luhn, SSN area/group rules, …) | `PII`, `PRIVACY`; spans per entity |
| Toxicity / bias | `toxicity_bias.detoxify+regard` | Detoxify `unbiased-small` (primary) **and** the `regardv3` classifier used both directly and as a demographic-swap differential (confirmatory) | `TOXICITY`, `BIAS` |
| Groundedness | `groundedness.nli` | Sentence-level claim extraction (spaCy) → cross-encoder NLI (`nli-deberta-v3-xsmall`) against the supplied source docs | `HALLUCINATION`; spans per contradicted / unsupported claim |

## No-false-fallback behaviour

- A detector that cannot run its mechanism returns `ok=False` (via
  `DetectionResult.failed`) — never a clean-looking result. The decision engine
  treats `ok=False` as *missing evidence* and routes to review.
- Toxicity: Detoxify is primary — its failure fails the detector. `regard` is
  confirmatory — its failure leaves `ok=True` but caps confidence and says so in
  the rationale (honest degradation).
- Groundedness with **no source documents** abstains: `evidence.assessable = False`,
  `confidence = 0` — it does not guess "grounded".
- When the two toxicity signals disagree, confidence is reduced and the rationale
  records the disagreement.

**Known limitation:** the regard-swap differential detects *differential* treatment
of groups; a symmetrically-phrased stereotype produces a small gap. Phase 5's
AI-as-judge adds an independent second opinion on bias.

## Tests

```bash
make test          # fast: contract only, no model downloads
make test-models   # the real-model suite (downloads ~2 GB of weights on first run)
```

The real-model suite runs in CI on `main` and via manual dispatch (cached), not on
every PR. Each detector has known-answer tests plus a fault-injection test
asserting the failure path returns `ok=False`.

## Inspect one input

```bash
python -m controlplane_detectors "the answer text" --source "a grounding document"
```
