import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from controlplane_gateway.audit.chain import compute_hash
from controlplane_gateway.audit.models import ActionRecord, AuditRecord, RetentionLogRecord
from controlplane_gateway.audit.store import AuditStore
from controlplane_gateway.config import get_settings


async def verify_chain(session: AsyncSession, model_cls: type, table_name: str) -> int:
    result = await session.execute(select(model_cls).order_by(model_cls.id.asc()))
    records = result.scalars().all()

    running_prev = None
    count = 0

    for row in records:
        count += 1

        # 1. Check prev_hash linkage
        if row.prev_hash != running_prev:
            print(
                f"FAIL: {table_name} id={row.id} prev_hash mismatch. "
                f"Expected {running_prev}, got {row.prev_hash}"
            )
            sys.exit(1)

        anonymized = getattr(row, "anonymized", False)

        if not anonymized:
            # 2. Check content hash
            computed = compute_hash(running_prev, row)
            if computed != row.record_hash:
                print(
                    f"FAIL: {table_name} id={row.id} record_hash mismatch. "
                    f"Expected {row.record_hash}, got {computed}"
                )
                sys.exit(1)
        else:
            # 3. Check tombstone for anonymized rows. ActionRecord carries
            # *both* request_id (its originating chat request) and its own
            # action_id — retention.py always tombstones it by action_id,
            # so a generic "request_id if present, else action_id" lookup
            # would silently match the wrong column and always miss. Key
            # off the table being verified instead, matching how the
            # tombstone was actually written.
            target_id = row.action_id if table_name == "action_records" else row.request_id

            tombstone_result = await session.execute(
                select(RetentionLogRecord)
                .where(
                    RetentionLogRecord.table_name == table_name,
                    RetentionLogRecord.target_id == target_id,
                    RetentionLogRecord.action == "anonymized",
                )
                .limit(1)
            )
            tombstone = tombstone_result.scalar_one_or_none()
            if not tombstone:
                print(
                    f"FAIL: {table_name} id={row.id} is anonymized "
                    "but missing RetentionLogRecord tombstone"
                )
                sys.exit(1)

        running_prev = row.record_hash

    return count


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--table", required=True, choices=["audit_records", "action_records", "retention_log"]
    )
    args = parser.parse_args()

    settings = get_settings()
    store = AuditStore(settings.database_url)

    model_map = {
        "audit_records": AuditRecord,
        "action_records": ActionRecord,
        "retention_log": RetentionLogRecord,
    }
    model_cls = model_map[args.table]

    try:
        async with store._session() as session:
            count = await verify_chain(session, model_cls, args.table)
            print(f"{count} records verified, chain intact")
    finally:
        await store.aclose()


if __name__ == "__main__":
    asyncio.run(main())
