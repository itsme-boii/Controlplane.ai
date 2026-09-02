# Policy packs

Versioned YAML consumed by the `controlplane_policy` engine. Resolution
deep-merges `base ← usecase ← jurisdiction` (later layers win) into one
content-hashed `EffectivePolicy`.

```
base.yaml                     default policy, fully specified
usecases/
  supportassist.yaml          fast path, 400 ms budget, privacy-critical
  knowledgecopilot.yaml       deep path, groundedness-weighted
  decisionsupport.yaml        deep path, strict thresholds, stricter decision table
jurisdictions/
  us.yaml                     baseline (base is already US-shaped)
  eu.yaml                     stricter overlay — GDPR + EU AI Act
```

Inspect a resolution:

```bash
python -m controlplane_policy list
python -m controlplane_policy resolve --usecase supportassist --geo eu
```

Each pack declares `meta.kind` (`base` | `usecase` | `jurisdiction`) and an
`effective_from` date. Unknown top-level keys are rejected at load time. The
decision table (`decision_rules`) is carried and merged here; it is *executed*
by the decision engine in Phase 4.
