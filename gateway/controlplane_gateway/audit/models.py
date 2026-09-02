"""Audit-record ORM model.

Phase 1 is the *skeleton*: one row per interaction with request/response,
latency and policy version. Phase 7 makes it tamper-evident (SHA-256 hash
chain, retention enforcement) and adds detector results and reviewer actions.
The columns already present here (``prev_hash`` / ``record_hash``) are wired in
Phase 7; Phase 1 leaves them null.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditRecord(Base):
    __tablename__ = "audit_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Request context
    usecase_id: Mapped[str | None] = mapped_column(String(128), index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(16))
    # Content-hashed id of the effective policy, plus the full resolved snapshot
    # so any decision is replayable and the version id is recomputable.
    policy_version: Mapped[str] = mapped_column(String(96))
    policy_snapshot: Mapped[dict | None] = mapped_column(JSON)
    model: Mapped[str | None] = mapped_column(String(128))

    # Payloads (kept as JSON for replayability)
    request_body: Mapped[dict] = mapped_column(JSON)
    # The full upstream model output — stored even when the caller never receives
    # it (a withheld review/block response).
    response_body: Mapped[dict | None] = mapped_column(JSON)

    # Phase 4: the evidence and the decision behind `decision`. `detector_results`
    # is the raw DetectionResult list; `decision_detail` is the aggregated
    # assessment, matched rule, redaction and any fail-safe overrides.
    detector_results: Mapped[list | None] = mapped_column(JSON)
    decision_detail: Mapped[dict | None] = mapped_column(JSON)

    # Outcome. `decision` is null until a real decision is made — on an upstream
    # failure it stays null rather than defaulting to a safe-looking "allow"
    # (no-false-fallback rule). On success it is the decision engine's tier
    # (allow / edit / review / block).
    decision: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | error
    error: Mapped[str | None] = mapped_column(Text)

    # Latency breakdown (ms)
    gateway_latency_ms: Mapped[float | None] = mapped_column()
    upstream_latency_ms: Mapped[float | None] = mapped_column()

    # Phase 7: Retention anonymization flags
    anonymized: Mapped[bool] = mapped_column(default=False)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Hash chain — populated in Phase 7
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    record_hash: Mapped[str | None] = mapped_column(String(64))


class ActionRecord(Base):
    __tablename__ = "action_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    action_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    action_decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    executed: Mapped[bool] = mapped_column(default=False)
    execution_result: Mapped[dict | None] = mapped_column(JSON)
    execution_error: Mapped[str | None] = mapped_column(Text)

    # Phase 7: Retention anonymization flags
    anonymized: Mapped[bool] = mapped_column(default=False)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Hash chain -- populated in Phase 7, same shape as AuditRecord's.
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    record_hash: Mapped[str | None] = mapped_column(String(64))


class RetentionLogRecord(Base):
    __tablename__ = "retention_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    table_name: Mapped[str] = mapped_column(String(32))  # "audit_records" | "action_records"
    target_id: Mapped[str] = mapped_column(String(64))  # request_id / action_id
    action: Mapped[str] = mapped_column(String(16))  # "anonymized"
    reason: Mapped[str] = mapped_column(Text)  # e.g. "retention_days=180 exceeded"
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    record_hash: Mapped[str | None] = mapped_column(String(64))

class ReviewRecord(Base):
    __tablename__ = "review_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(32))       # e.g., "approve", "reject", "edit"
    notes: Mapped[str | None] = mapped_column(Text)
    edited_text: Mapped[str | None] = mapped_column(Text)
    
    # Hash chain
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    record_hash: Mapped[str | None] = mapped_column(String(64))

class EvalRunRecord(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    total_examples: Mapped[int] = mapped_column(Integer)
    precision: Mapped[float] = mapped_column(Float)
    recall: Mapped[float] = mapped_column(Float)
    f1_score: Mapped[float] = mapped_column(Float)
    fp_rate: Mapped[float] = mapped_column(Float)
    fn_rate: Mapped[float] = mapped_column(Float)
    metrics_detail: Mapped[dict | None] = mapped_column(JSON)
