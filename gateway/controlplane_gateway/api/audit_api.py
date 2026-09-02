import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from controlplane_gateway.api.deps import AuditStoreDep
from controlplane_gateway.audit.models import AuditRecord, ReviewRecord

router = APIRouter(prefix="/v1", tags=["audit"])


class ReviewRequest(BaseModel):
    action: str
    notes: str | None = None
    edited_text: str | None = None
    reviewer_id: str = "system"


class ReviewResponse(BaseModel):
    status: str
    id: int


@router.get("/audit/records")
async def list_records(
    audit_store: AuditStoreDep,
    tier: str | None = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    async with audit_store._session() as session:
        stmt = select(AuditRecord).order_by(AuditRecord.id.desc()).limit(limit).offset(offset)
        if tier:
            stmt = stmt.where(AuditRecord.decision == tier)

        result = await session.execute(stmt)
        records = result.scalars().all()

        return [
            {
                "id": r.id,
                "request_id": r.request_id,
                "created_at": r.created_at,
                "decision": r.decision,
                "usecase_id": r.usecase_id,
            }
            for r in records
        ]


@router.get("/audit/records/{request_id}")
async def get_record(request_id: str, audit_store: AuditStoreDep):
    async with audit_store._session() as session:
        result = await session.execute(
            select(AuditRecord).where(AuditRecord.request_id == request_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Not found")

        # Get reviews
        review_result = await session.execute(
            select(ReviewRecord)
            .where(ReviewRecord.request_id == request_id)
            .order_by(ReviewRecord.created_at.asc())
        )
        reviews = review_result.scalars().all()

        return {
            "record": {
                "request_id": record.request_id,
                "created_at": record.created_at,
                "usecase_id": record.usecase_id,
                "jurisdiction": record.jurisdiction,
                "policy_version": record.policy_version,
                "model": record.model,
                "request_body": record.request_body,
                "response_body": record.response_body,
                "detector_results": record.detector_results,
                "decision_detail": record.decision_detail,
                "decision": record.decision,
                "status": record.status,
                "error": record.error,
                "gateway_latency_ms": record.gateway_latency_ms,
                "upstream_latency_ms": record.upstream_latency_ms,
                "anonymized": getattr(record, "anonymized", False),
            },
            "reviews": [
                {
                    "created_at": r.created_at,
                    "reviewer_id": r.reviewer_id,
                    "action": r.action,
                    "notes": r.notes,
                    "edited_text": r.edited_text,
                }
                for r in reviews
            ],
        }


@router.post("/audit/records/{request_id}/review")
async def create_review(
    request_id: str, body: ReviewRequest, audit_store: AuditStoreDep
) -> ReviewResponse:
    record = await audit_store.get_by_request_id(request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")

    review = ReviewRecord(
        created_at=datetime.now(timezone.utc),
        request_id=request_id,
        reviewer_id=body.reviewer_id,
        action=body.action,
        notes=body.notes,
        edited_text=body.edited_text,
    )

    await audit_store.write_review(review)
    return ReviewResponse(status="ok", id=review.id)


_stream_queues: list[asyncio.Queue] = []


def broadcast_record(record_dict: dict):
    for q in _stream_queues:
        q.put_nowait(record_dict)


@router.get("/audit/stream")
async def stream_records(request: Request):
    q = asyncio.Queue()
    _stream_queues.append(q)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                # Use a small timeout so we can check for disconnects frequently
                try:
                    record = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield f"data: {json.dumps(record)}\n\n"
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            if q in _stream_queues:
                _stream_queues.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/metrics/eval-runs")
async def get_eval_runs(audit_store: AuditStoreDep, limit: int = Query(20, le=100)):
    async with audit_store._session() as session:
        from controlplane_gateway.audit.models import EvalRunRecord
        result = await session.execute(
            select(EvalRunRecord).order_by(EvalRunRecord.id.desc()).limit(limit)
        )
        records = result.scalars().all()
        return [
            {
                "run_id": r.run_id,
                "created_at": r.created_at,
                "total_examples": r.total_examples,
                "precision": r.precision,
                "recall": r.recall,
                "f1_score": r.f1_score,
                "fp_rate": r.fp_rate,
                "fn_rate": r.fn_rate,
            } for r in reversed(records) # Return chronologically for charting
        ]

@router.get("/metrics/stats")
async def get_stats(audit_store: AuditStoreDep):
    async with audit_store._session() as session:
        from sqlalchemy import func
        from controlplane_gateway.audit.models import AuditRecord, ReviewRecord
        
        total_blocks = (await session.execute(
            select(func.count(AuditRecord.id)).where(AuditRecord.decision == "block")
        )).scalar() or 0
        
        total_overrides = (await session.execute(
            select(func.count(ReviewRecord.id)).where(ReviewRecord.action.in_(["approve", "edit"]))
        )).scalar() or 0
        
        override_rate = total_overrides / total_blocks if total_blocks > 0 else 0
        
        return {
            "total_blocks": total_blocks,
            "total_overrides": total_overrides,
            "override_rate": override_rate
        }
