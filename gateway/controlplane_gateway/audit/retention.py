from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select

from controlplane_gateway.audit.models import ActionRecord, AuditRecord, RetentionLogRecord
from controlplane_gateway.audit.store import AuditStore


class RetentionReport(BaseModel):
    scanned: int = 0
    anonymized: int = 0
    already_anonymized: int = 0
    errors: list[str] = []


async def run_retention_sweep(store: AuditStore, now: datetime | None = None) -> RetentionReport:
    """For each non-anonymized AuditRecord, read retention_days from its own
    policy_snapshot (already stored per-record since Phase 2/4 -- this is the record's *own*
    policy at the time it was decided, not today's policy, which matters if a policy pack's
    retention window changes later). created_at + retention_days <= now -> anonymize:
      1. write a chained RetentionLogRecord first.
      2. null request_body/response_body/policy_snapshot (or replace with a small
         redaction marker dict, not literal SQL NULL, so downstream JSON consumers don't
         need special-casing), set anonymized=True, anonymized_at=now.
    """
    if now is None:
        now = datetime.now(UTC)

    report = RetentionReport()
    redaction_marker = {"redacted": True, "reason": "retention"}

    def _retention_days_from(snapshot: object) -> int | None:
        """Extract retention_days from a policy_snapshot, or None if the
        snapshot doesn't actually carry one (missing, already redacted, or
        unparseable) — never a fabricated number."""
        if isinstance(snapshot, dict):
            if snapshot.get("redacted"):
                return None
            value = snapshot.get("retention_days")
            return value if isinstance(value, int) else None
        if isinstance(snapshot, str):
            try:
                return _retention_days_from(json.loads(snapshot))
            except json.JSONDecodeError:
                return None
        return None

    def _age_days(created_at: datetime) -> int:
        # Some DB backends (SQLite, notably) don't round-trip tzinfo through
        # DateTime(timezone=True) — a value written as UTC-aware can come
        # back naive. Treat a naive read-back as UTC rather than letting the
        # subtraction below raise (or, worse, comparing against the wrong
        # wall-clock zone).
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return (now - created_at).days

    async with store._session() as session:
        # ActionRecords are swept *before* AuditRecords: an action's own
        # retention window is derived from its parent audit record's
        # policy_snapshot (an action carries no policy_snapshot of its
        # own), so it must be read while that snapshot is still intact.
        # Sweeping AuditRecords first would redact the very field this pass
        # depends on for any action written in the same run.
        action_result = await session.execute(
            select(ActionRecord).where(ActionRecord.anonymized == False)  # noqa: E712
        )
        action_records = action_result.scalars().all()

        for record in action_records:
            report.scanned += 1
            try:
                # Find the corresponding audit record to read its policy.
                audit_rec = await store.get_by_request_id(record.request_id)
                retention_days = _retention_days_from(
                    audit_rec.policy_snapshot if audit_rec else None
                )
                if retention_days is None:
                    # Parent audit record missing or already anonymized —
                    # its policy_snapshot (the only source of this action's
                    # retention window) is gone. Guessing a number here
                    # (e.g. a hardcoded fallback) would fabricate a
                    # retention decision with no real evidence behind it —
                    # exactly the kind of quiet fallback this project
                    # forbids — so this record is left untouched and
                    # surfaced for a human, not silently redacted or kept.
                    report.errors.append(
                        f"ActionRecord {record.action_id}: cannot determine retention_days "
                        "(parent audit record missing or already anonymized)"
                    )
                    continue

                age_days = _age_days(record.created_at)
                if age_days >= retention_days:
                    # Anonymize
                    log = RetentionLogRecord(
                        table_name="action_records",
                        target_id=record.action_id,
                        action="anonymized",
                        reason=f"retention_days={retention_days} exceeded",
                        created_at=now,
                    )
                    await store.write_retention_log(log)

                    # Redact content
                    record.payload = redaction_marker
                    record.execution_result = redaction_marker
                    record.anonymized = True
                    record.anonymized_at = now
                    session.add(record)
                    await session.commit()
                    report.anonymized += 1
            except Exception as e:
                report.errors.append(f"ActionRecord {record.action_id}: {e}")
                await session.rollback()

        # Sweep AuditRecords
        audit_result = await session.execute(
            select(AuditRecord).where(AuditRecord.anonymized == False)  # noqa: E712
        )
        audit_records = audit_result.scalars().all()

        for record in audit_records:
            report.scanned += 1
            try:
                retention_days = _retention_days_from(record.policy_snapshot) or 365

                age_days = _age_days(record.created_at)
                if age_days >= retention_days:
                    # Anonymize
                    log = RetentionLogRecord(
                        table_name="audit_records",
                        target_id=record.request_id,
                        action="anonymized",
                        reason=f"retention_days={retention_days} exceeded",
                        created_at=now,
                    )
                    await store.write_retention_log(log)

                    # Redact content
                    record.request_body = redaction_marker
                    record.response_body = redaction_marker
                    record.policy_snapshot = redaction_marker
                    record.anonymized = True
                    record.anonymized_at = now
                    session.add(record)
                    await session.commit()
                    report.anonymized += 1
            except Exception as e:
                report.errors.append(f"AuditRecord {record.request_id}: {e}")
                await session.rollback()

    return report
