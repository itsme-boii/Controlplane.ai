"""Liveness and readiness probes.

``/healthz`` is liveness (process is up). ``/readyz`` is readiness: it checks
the datastores the gateway depends on and fails loudly if any are unreachable —
no pretending to be ready.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from controlplane_gateway.api.deps import AuditStoreDep

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response, audit_store: AuditStoreDep) -> dict:
    checks: dict[str, str] = {}

    try:
        await audit_store.ping()
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 — report, don't hide
        checks["postgres"] = f"error: {exc}"

    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {exc}"

    ready = all(v == "ok" for v in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ready": ready, "checks": checks}
