"""Application factory and lifecycle wiring."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from controlplane_decision import DecisionEngine
from controlplane_detectors import default_detectors, warmup
from controlplane_policy import PolicyEngine, PolicyRepo
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from controlplane_gateway import __version__
from controlplane_gateway.actions.mailtrap import MailtrapClient
from controlplane_gateway.api import actions, audit_api, chat, health, policy_api
from controlplane_gateway.audit import AuditStore
from controlplane_gateway.config import Settings, get_settings
from controlplane_gateway.ledger.store import RedisLedgerStore
from controlplane_gateway.models import build_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    log = logging.getLogger("controlplane.gateway")

    # Fail fast on misconfiguration — better a dead startup than a running
    # gateway that 502s every call or resolves no policy.
    app.state.provider = build_provider(settings)
    app.state.policy_engine = PolicyEngine(PolicyRepo.from_dir(settings.policies_dir))

    app.state.detectors = default_detectors()
    app.state.decision_engine = DecisionEngine()
    if settings.detector_warmup:
        # Blocking model loads — do them off the event loop, but before we serve.
        await asyncio.to_thread(warmup)

    app.state.audit_store = AuditStore(settings.database_url)
    await app.state.audit_store.init_schema()

    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    app.state.ledger_store = RedisLedgerStore(app.state.redis, settings.ledger_ttl_seconds)

    # One long-lived Mailtrap client for the process, same lifecycle as the
    # model provider — actions.py falls back to a per-call client only if
    # this isn't set (e.g. in tests that don't run lifespan).
    app.state.mailtrap_client = MailtrapClient(
        settings.mailtrap_api_token, settings.mailtrap_inbox_id
    )

    log.info(
        "gateway %s ready (provider=%s, usecases=%s, detectors=%s)",
        __version__,
        app.state.provider.name,
        app.state.policy_engine.usecases,
        [d.name for d in app.state.detectors],
    )
    try:
        yield
    finally:
        await app.state.provider.aclose()
        await app.state.audit_store.aclose()
        await app.state.mailtrap_client.aclose()
        await app.state.redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ControlPlane.ai Gateway",
        version=__version__,
        summary="OpenAI-compatible governance gateway: policy, detectors, tiered decision, audit",
        lifespan=lifespan,
    )
    # The Next.js review console runs on a different origin (localhost:3000)
    # and calls this gateway directly from the browser (fetch + EventSource),
    # including the X-Usecase-Id / X-Jurisdiction / X-Conversation-Id headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(actions.router)
    app.include_router(audit_api.router)
    app.include_router(policy_api.router)
    return app


app = create_app()
