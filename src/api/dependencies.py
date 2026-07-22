from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Request

from src.api.schemas.decisions import DecisionRequest
from src.api.security import validate_security_settings
from src.engine import DecisionService
from src.engine.schemas import EngineRequest


def create_lifespan(decision_service: DecisionService | None = None):
    @asynccontextmanager
    async def lifespan(app):
        from src.core.config import load_settings

        validate_security_settings(load_settings())
        app.state.decision_service = decision_service or DecisionService.from_files()
        yield

    return lifespan


def get_decision_service(request: Request) -> DecisionService:
    service = getattr(request.app.state, "decision_service", None)
    if service is None:
        service = DecisionService.from_files()
        request.app.state.decision_service = service
    return service


def to_engine_request(payload: DecisionRequest) -> EngineRequest:
    return EngineRequest(
        request_id=payload.request_id,
        customer_context=payload.customer_context.model_dump(exclude_none=True, mode="json"),
        eligible_offers=[offer.value for offer in payload.eligible_offers],
    )
