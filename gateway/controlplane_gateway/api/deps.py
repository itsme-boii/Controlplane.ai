"""FastAPI dependencies exposing resources held on ``app.state``."""

from __future__ import annotations

from typing import Annotated

from controlplane_decision import DecisionEngine
from controlplane_detectors import Detector
from controlplane_policy import PolicyEngine
from fastapi import Depends, Request

from controlplane_gateway.audit import AuditStore
from controlplane_gateway.ledger.store import RedisLedgerStore
from controlplane_gateway.models import ModelProvider


def get_provider(request: Request) -> ModelProvider:
    return request.app.state.provider


def get_audit_store(request: Request) -> AuditStore:
    return request.app.state.audit_store


def get_policy_engine(request: Request) -> PolicyEngine:
    return request.app.state.policy_engine


def get_detectors(request: Request) -> list[Detector]:
    return request.app.state.detectors


def get_decision_engine(request: Request) -> DecisionEngine:
    return request.app.state.decision_engine


def get_ledger_store(request: Request) -> RedisLedgerStore:
    return request.app.state.ledger_store


ProviderDep = Annotated[ModelProvider, Depends(get_provider)]
AuditStoreDep = Annotated[AuditStore, Depends(get_audit_store)]
PolicyEngineDep = Annotated[PolicyEngine, Depends(get_policy_engine)]
DetectorsDep = Annotated[list[Detector], Depends(get_detectors)]
DecisionEngineDep = Annotated[DecisionEngine, Depends(get_decision_engine)]
LedgerStoreDep = Annotated[RedisLedgerStore, Depends(get_ledger_store)]
