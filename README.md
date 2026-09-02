# ControlPlane.ai

**Institutional-Grade AI Governance and Security Gateway**

ControlPlane.ai is a comprehensive, open-source governance platform designed to sit between enterprise applications and upstream Large Language Models (LLMs). It acts as an intelligent firewall and audit layer, ensuring that all AI interactions comply with organizational policies, data privacy laws, and security standards before they ever reach the model.

---

## 🌟 Key Features

*   **Policy-Driven Routing (Tiered Enforcement)**: Define YAML policies (Allow, Edit, Review, Block) specific to different use cases (e.g., internal tools vs. customer-facing agents).
*   **Multi-Layer Detection Engine**: Identifies PII, Toxicity, Prompt Injections, and Jailbreaks via local lightweight models and LLM-as-a-judge capabilities.
*   **Cryptographic Audit Trail**: Every interaction is permanently logged in a PostgreSQL database using a SHA-256 hash-chain, guaranteeing tamper-evident records for compliance audits.
*   **Human-in-the-Loop Review Console**: A Next.js dashboard where auditors can stream live traffic, review blocked interactions, and manually override decisions.
*   **Continuous Evaluation (Data Flywheel)**: Human overrides are automatically synced back into an evaluation corpus to recalculate F1 metrics and dynamically tune policy thresholds.

---

## 🏗 System Architecture

The repository is modularized into strictly separated domains:

1.  **`gateway/`**: The FastAPI application serving OpenAI-compatible endpoints (`/v1/chat/completions`) and routing traffic through the evaluation pipeline.
2.  **`policy/`**: The schema definitions and resolvers for usecase-based YAML configurations.
3.  **`detectors/`**: The analysis modules running asynchronous checks (Presidio, LLM-Judge) against prompts and responses.
4.  **`decision/`**: The deterministic engine that compares detector evidence against policy thresholds to yield a final enforcement tier.
5.  **`web/`**: The Next.js 14 frontend console for live SSE streaming, metric tracking, and manual interaction review.

For deep technical details on the data flow, please see [`docs/architecture.md`](docs/architecture.md).

---

## 🚀 Getting Started (Local Development)

### Prerequisites
* Docker & Docker Compose
* Python 3.11+ (managed via `uv`)
* Node.js & pnpm

### 1. Environment Setup
Clone the repository and set up your API keys.
```bash
cp .env.example .env
# Edit .env to add your GROQ_API_KEY
```

### 2. Start the Backend Infrastructure
Launch PostgreSQL and Redis, followed by the FastAPI gateway.
```bash
docker-compose up -d
make up
```
*The gateway is now available at `http://localhost:8000`.*

### 3. Start the Next.js Review Console
In a separate terminal, launch the frontend dashboard.
```bash
cd web
pnpm install
pnpm dev
```
*The console is now available at `http://localhost:3000`.*

### 4. Simulate Traffic
To see the system in action, generate traffic using our smoke testing script:
```bash
./scripts/smoke.sh
```
Navigate to the Live Feed on the Review Console to watch the interactions get evaluated and chained in real-time.

---

## 🛡 Compliance & Security

ControlPlane.ai is built with stringent compliance requirements in mind:
*   **Data Retention**: Configurable time-to-live (TTL) sweeps anonymize old records while leaving cryptographic tombstones to preserve chain integrity.
*   **Replayability**: All policy snapshots are saved at the time of the interaction, meaning any historical decision can be mathematically proven and replayed.

---

## 📄 License
This project is licensed under the MIT License. See the `LICENSE` file for details.
