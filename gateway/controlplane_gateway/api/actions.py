from __future__ import annotations

import uuid
from typing import Annotated

from controlplane_decision.engine import Decision
from controlplane_policy import EffectivePolicy, Tier
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from controlplane_gateway.actions.gate import ActionGate
from controlplane_gateway.actions.mailtrap import ActionExecutionError, MailtrapClient
from controlplane_gateway.api.deps import AuditStoreDep, LedgerStoreDep
from controlplane_gateway.audit.models import ActionRecord
from controlplane_gateway.config import Settings, get_settings
from controlplane_gateway.schemas.actions import ActionRequest, ActionResponse

router = APIRouter(prefix="/v1", tags=["actions"])


@router.post("/actions/execute")
async def execute_action(
    request: Request,
    response: Response,
    body: ActionRequest,
    audit_store: AuditStoreDep,
    ledger_store: LedgerStoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ActionResponse:
    action_id = f"act_{uuid.uuid4().hex}"

    # 1. Fetch chat record
    audit_record = await audit_store.get_by_request_id(body.request_id)
    if not audit_record:
        raise HTTPException(status_code=404, detail="originating chat record not found")

    # 2. Reconstruct Decision and Policy
    try:
        policy = EffectivePolicy.model_validate(audit_record.policy_snapshot)
        text_decision = Decision.model_validate(audit_record.decision_detail)
    except (ValidationError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=500, detail=f"failed to reconstruct originating context: {e}"
        ) from e

    # 3. Fetch LedgerState
    ledger_state = None
    if body.conversation_id and settings.ledger_enabled:
        ledger_state = await ledger_store.get(body.conversation_id)

    # 4. ActionGate
    gate = ActionGate()
    decision = gate.evaluate(body.action_type, policy, text_decision, ledger_state)

    action_record = ActionRecord(
        action_id=action_id,
        request_id=body.request_id,
        conversation_id=body.conversation_id,
        action_type=body.action_type,
        payload=body.payload,
        action_decision=decision.tier.value,
        reason=decision.reason,
        executed=False,
    )

    result = None
    execution_error = None

    if decision.tier == Tier.ALLOW:
        if body.action_type == "send_email":
            client = getattr(request.app.state, "mailtrap_client", None)
            if not client:
                client = MailtrapClient(settings.mailtrap_api_token, settings.mailtrap_inbox_id)

            to = body.payload.get("to", "")
            subject = body.payload.get("subject", "")
            body_text = body.payload.get("body", "")

            try:
                result = await client.send_email(to, subject, body_text)
                action_record.executed = True
                action_record.execution_result = result
            except ActionExecutionError as e:
                action_record.executed = False
                execution_error = str(e)
                action_record.execution_error = execution_error
            except Exception as e:
                action_record.executed = False
                execution_error = f"Unhandled error: {e}"
                action_record.execution_error = execution_error
        else:
            action_record.executed = False
            execution_error = f"unknown action_type {body.action_type}"
            action_record.execution_error = execution_error

    # Save ActionRecord
    try:
        await audit_store.write_action(action_record)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"audit logging failed: {e}") from e

    if execution_error:
        response.status_code = status.HTTP_502_BAD_GATEWAY
        return ActionResponse(
            action_id=action_id,
            action_decision=decision.tier.value,
            executed=False,
            reason=f"Action execution failed: {execution_error}",
        )

    return ActionResponse(
        action_id=action_id,
        action_decision=decision.tier.value,
        executed=bool(action_record.executed),
        result=result,
        reason=decision.reason,
    )
