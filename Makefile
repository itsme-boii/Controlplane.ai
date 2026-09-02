.PHONY: help install lint typecheck test test-models check up down logs smoke eval-run web-install web-dev

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

install: ## Install every package into its local venv (uv)
	cd gateway && uv sync --extra dev
	cd detectors && uv sync --extra dev --extra ml
	cd policy && uv sync --extra dev
	cd decision && uv sync --extra dev
	@echo "note: the gateway runs real detectors only with the ml extra —"
	@echo "      'cd gateway && uv sync --extra dev --extra ml' (Docker does this)."

lint: ## Ruff lint
	cd gateway && uv run ruff check . && uv run ruff format --check .
	cd detectors && uv run --extra dev ruff check . && uv run --extra dev ruff format --check .
	cd policy && uv run ruff check . && uv run ruff format --check .
	cd decision && uv run ruff check . && uv run ruff format --check .

typecheck: ## mypy on the gateway and decision packages
	cd gateway && uv run mypy controlplane_gateway
	cd decision && uv run mypy controlplane_decision

test: ## Run the fast unit suites (no model downloads)
	cd gateway && uv run pytest -q
	cd detectors && uv run --extra dev pytest -q -m "not models"
	cd policy && uv run pytest -q
	cd decision && uv run pytest -q

test-models: ## Run the detector suites that exercise real ML models (downloads weights)
	cd detectors && uv run --extra dev --extra ml pytest -q -m models

check: lint typecheck test ## Everything CI runs

up: ## Start the full stack
	docker compose up --build -d

down: ## Stop the stack
	docker compose down

logs: ## Tail gateway logs
	docker compose logs -f gateway

smoke: ## End-to-end: real request through the running gateway (needs GROQ_API_KEY in .env)
	./scripts/smoke.sh

# Both targets below run on the host against the dockerized Postgres, so
# DATABASE_URL needs the host-mapped port (5433) — .env's own DATABASE_URL
# targets the in-network hostname (postgres:5432), which only resolves from
# inside the compose network, not from the host running `uv run` here.
HOST_DATABASE_URL := postgresql+asyncpg://controlplane:controlplane@localhost:5433/controlplane

retention-sweep: ## Run the retention job against the live audit store
	cd gateway && DATABASE_URL=$(HOST_DATABASE_URL) uv run python -m controlplane_gateway.audit.retention

eval-run: ## Score evals/corpus/*.jsonl against the real running gateway, record real precision/recall/F1
	cd gateway && DATABASE_URL=$(HOST_DATABASE_URL) uv run python ../scripts/eval_runner.py

web-install: ## Install the Next.js console deps
	cd web && pnpm install

web-dev: ## Run the Next.js console in dev mode
	cd web && pnpm dev
