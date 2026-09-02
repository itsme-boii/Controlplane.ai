#!/usr/bin/env python3
import asyncio
import json
import sys
from pathlib import Path

async def main():
    root = Path(__file__).parent.parent
    corpus_dir = root / "evals" / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    
    overrides_file = corpus_dir / "overrides.jsonl"
    
    sys.path.insert(0, str(root / "gateway"))
    from controlplane_gateway.audit.models import ReviewRecord, AuditRecord
    from controlplane_gateway.audit.store import AuditStore
    from controlplane_gateway.config import get_settings
    from sqlalchemy import select
    
    settings = get_settings()
    audit_store = AuditStore(settings.database_url)
    
    new_overrides = []
    
    async with audit_store._session() as session:
        # Get all review records that modified the decision
        result = await session.execute(
            select(ReviewRecord, AuditRecord)
            .join(AuditRecord, ReviewRecord.request_id == AuditRecord.request_id)
            .order_by(ReviewRecord.created_at.asc())
        )
        
        for review, audit in result.all():
            # If a human reviewer overrides a block, they think it should be allowed
            expected_tier = "allow" if review.action in ("approve", "edit") else "block"
            
            prompt = audit.request_body.get("messages", [{}])[-1].get("content", "")
            if not prompt:
                continue
                
            entry = {
                "prompt": prompt,
                "expected_flag": None if expected_tier == "allow" else "unknown",
                "expected_tier": expected_tier,
                "source": "human_override",
                "request_id": review.request_id
            }
            new_overrides.append(entry)
            
    # In a real app, we would deduplicate or avoid writing the same ones repeatedly.
    # For now, we overwrite.
    with open(overrides_file, "w") as f:
        for entry in new_overrides:
            f.write(json.dumps(entry) + "\n")
            
    await audit_store.aclose()
    print(f"Synced {len(new_overrides)} overrides into {overrides_file}")

if __name__ == "__main__":
    asyncio.run(main())
