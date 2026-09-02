from __future__ import annotations

from datetime import UTC

from controlplane_policy.hashing import content_hash

from controlplane_gateway.audit.models import ActionRecord, AuditRecord, RetentionLogRecord, ReviewRecord

_CHAINABLE_FIELDS = {
    AuditRecord: [
        "request_id",
        "created_at",
        "usecase_id",
        "jurisdiction",
        "policy_version",
        "model",
        "request_body",
        "response_body",
        "detector_results",
        "decision_detail",
        "decision",
        "status",
        "error",
    ],
    ActionRecord: [
        "action_id",
        "request_id",
        "conversation_id",
        "created_at",
        "action_type",
        "payload",
        "action_decision",
        "reason",
        "executed",
        "execution_result",
        "execution_error",
    ],
    RetentionLogRecord: [
        "created_at",
        "table_name",
        "target_id",
        "action",
        "reason",
    ],
    ReviewRecord: [
        "created_at",
        "request_id",
        "reviewer_id",
        "action",
        "notes",
        "edited_text",
    ],
}


def record_fields(record) -> dict:
    """The subset of a record's columns that go into its hash -- excludes id/prev_hash/record_hash
    themselves (id is storage-order; hash fields are the output),
    and excludes anonymized_at/anonymized (7.2) since those are metadata about the chain entry.
    """
    model_cls = type(record)
    fields = _CHAINABLE_FIELDS.get(model_cls)
    if not fields:
        raise ValueError(f"Unknown chainable model {model_cls}")

    out = {}
    for f in fields:
        val = getattr(record, f, None)
        # Convert datetime objects to isoformat for hashing. Normalize to
        # UTC-aware first: not every DB backend round-trips tzinfo through
        # DateTime(timezone=True) the same way (SQLite in particular hands
        # back a naive datetime for a value written as UTC-aware) — without
        # this, the same instant hashes differently depending on whether the
        # record was just written (in-memory, aware) or re-read for
        # verification (from-DB, possibly naive), which would make the
        # chain verifier report a false tamper on every row. Every
        # created_at in this codebase is UTC by convention, so a naive
        # value is always treated as UTC, never local time.
        if hasattr(val, "isoformat"):
            if val.tzinfo is None:
                val = val.replace(tzinfo=UTC)
            val = val.isoformat()
        out[f] = val
    return out


def compute_hash(prev_hash: str | None, record) -> str:
    payload = {"prev_hash": prev_hash, **record_fields(record)}
    return content_hash(payload)
