# Decision engine

Turns the detector library's `DetectionResult` list plus a resolved
`EffectivePolicy` into one tiered decision — **allow / edit / review / block** —
with the evidence attached and the *no-false-fallback* rule enforced in code, not
just in policy.

```python
from controlplane_decision import DecisionEngine

decision = DecisionEngine().decide(answer_text, detector_results, effective_policy)
decision.tier  # Tier.ALLOW | EDIT | REVIEW | BLOCK
decision.released_text_allowed  # False for review/block — do not return the model output
decision.redaction.text  # for the edit tier: the answer with PII spans masked
decision.assessment  # per-category risk, failed detectors, unassessable checks
decision.rationale  # which rule fired, and any fail-safe override
```

## Pipeline

1. **Aggregate** (`aggregate.py`) — collapse the multi-label detector results into
   one `CategoryRisk` per category: worst severity seen, and a confidence that
   rises when independent detectors agree (noisy-OR). Results for a check the
   policy disabled are dropped; failed detectors and abstentions
   (`assessable: false`) are tracked separately from clean passes.
2. **Evaluate the decision table** (`rules.py`) — `policy.decision_rules`, authored
   in YAML, tried top to bottom, first match wins. Predicates: `always`,
   `category` (+ `min_severity`, `only`), `detector_failed`, `confidence_below`.
   No implicit rows are added here.
3. **Fail-safe overrides** (`engine.py`) — applied after the table, independent of
   how the policy is written:
   - any detector that could not complete → never `allow`/`edit` → `review`;
   - the table matched no row → `review`;
   - `allow` but confidence below the policy's `confidence_floor` → `review`;
   - `edit` but nothing is actually maskable → `review` (we will not ship a
     response we claimed to sanitise).
4. **Redact** (`redact.py`) — for a surviving `edit`, mask each in-scope PII span
   with the policy's `mask_char`, right-to-left so offsets stay valid. Entity
   types outside `policy.pii.entities` are left in place and reported.

## The no-false-fallback exit gate

`tests/test_failsafe.py` is the concrete test for the governing rule
(`docs/discussion.md` Phase 4) and runs on every PR. Every path where evidence is
missing, incomplete, or low-confidence must land on `review` or stricter — proven,
not documented. The gateway-level half (a detector killed mid-request over the
real endpoint) is in `gateway/tests/test_chat_decision.py`.

## CLI

Pipe the detector CLI straight in:

```bash
python -m controlplane_detectors "The Eiffel Tower is in Berlin." \
    --source "The Eiffel Tower is in Paris, France." \
  | python -m controlplane_decision --usecase knowledgecopilot --geo eu \
      --response-text "The Eiffel Tower is in Berlin."
```

```bash
make test   # from the repo root — fast, no models
```
