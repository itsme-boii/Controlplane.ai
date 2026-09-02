# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Local path dependencies; copy each project plus the policy packs.
COPY detectors /app/detectors
COPY policy /app/policy
COPY decision /app/decision
COPY policies /app/policies
COPY gateway /app/gateway

WORKDIR /app/gateway
# The running service executes detectors in-process, so install the ml extra —
# `uv sync` honours detectors/'s CPU-only torch index from the lockfile.
RUN uv sync --frozen --no-dev --extra ml

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "controlplane_gateway.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
