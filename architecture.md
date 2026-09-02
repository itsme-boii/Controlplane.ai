# ControlPlane.ai Architecture Document

## Summary
ControlPlane.ai is an intelligent middleware layer sitting between client applications and upstream Large Language Models (LLMs). It provides a unified control plane to enforce security policies, detect anomalies (like PII leaks or prompt injections), and maintain a cryptographically secure audit trail. It enables enterprises to adopt generative AI safely by ensuring no prompt or response violates internal guidelines without being intercepted.

## What is Implemented
1. **OpenAI-Compatible Gateway**: A FastAPI backend that acts as a drop-in proxy for standard LLM SDKs (e.g., `openai` Python package).
2. **Dynamic Policy Engine**: YAML-based configuration engine allowing different strictness levels for different usecases (e.g., `decisionsupport` vs `customer_agent`).
3. **Multi-Detector Suite**: Implementations for Microsoft Presidio (PII redaction) and LLM-as-a-judge (Prompt Injection / Toxicity).
4. **Deterministic Decision Engine**: A tiered matrix logic (Allow, Edit, Review, Block) that weighs detector outputs against policy thresholds.
5. **Cryptographic Audit Store**: A Postgres-backed hash-chained ledger that proves the integrity of every logged interaction and human override.
6. **Continuous Evaluation Loop**: Automated scripts (`eval_runner.py`, `tuner.py`) that test policies against labeled datasets to output precision/recall metrics.
7. **Next.js Review Console**: A graphical dashboard featuring live SSE traffic streaming, an override queue for auditors, and dynamic KPI charts via Recharts.

## How it Works
1. **Interception**: A client application makes an LLM request to the Gateway instead of OpenAI/Groq directly.
2. **Context Resolution**: The Gateway inspects the payload headers to identify the `usecase` (e.g., internal-chat) and retrieves the corresponding YAML policy.
3. **Detector Phase**: The prompt is analyzed asynchronously by all active detectors (PII, Toxicity). 
4. **Decision Phase**: The Decision Engine compares the detector confidence scores against the YAML policy constraints. 
5. **Enforcement**:
   - If **Allow**: The prompt is passed to the upstream LLM. The LLM's response undergoes the exact same Detector -> Decision cycle before being returned to the user.
   - If **Edit**: Detected PII is redacted, and the sanitized prompt is sent upstream.
   - If **Block**: The request is dropped instantly, and a predefined error is returned.
   - If **Review**: The request is blocked for the user but flagged in the database for human review.
6. **Auditing**: Every step, latency metric, and decision is written to Postgres, securely linked to the previous interaction via a SHA-256 hash.

## User Flow with Example

**Scenario**: An employee using an internal AI tool tries to summarize a document containing a customer's Social Security Number (SSN).

1. **Client Request**: Employee application sends a prompt: *"Summarize this user profile: John Doe, SSN 123-45-678"*.
2. **Gateway Interception**: The FastAPI Gateway receives the prompt. It identifies the `usecase` as `internal_tool`.
3. **Detection**: The Presidio detector scans the prompt and flags an SSN entity with 0.95 confidence.
4. **Decision**: The YAML policy for `internal_tool` dictates that PII with confidence > 0.85 must trigger an **Edit** action.
5. **Enforcement**: The Gateway redacts the SSN. The modified prompt sent to the LLM becomes: *"Summarize this user profile: John Doe, SSN <REDACTED>"*.
6. **Upstream Processing**: The LLM summarizes the safe text and returns the response to the Gateway.
7. **Audit Logging**: The Gateway writes the original prompt, the redacted prompt, the detector scores, and the final LLM response into the PostgreSQL database as a cryptographically chained `AuditRecord`.
8. **Live Console**: An administrator looking at the Next.js Review Console sees the transaction appear instantly in the Live Feed, badged in orange as **EDITED**.
