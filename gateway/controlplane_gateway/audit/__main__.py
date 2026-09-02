import asyncio
import logging

from controlplane_gateway.audit.retention import run_retention_sweep
from controlplane_gateway.audit.store import AuditStore
from controlplane_gateway.config import get_settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("controlplane.retention")


async def main():
    settings = get_settings()
    store = AuditStore(settings.database_url)

    try:
        report = await run_retention_sweep(store)
        log.info(f"Retention sweep complete: {report.model_dump_json(indent=2)}")
    finally:
        await store.aclose()


if __name__ == "__main__":
    asyncio.run(main())
