from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Request

from src.api.schemas.decisions import DecisionRequest
from src.api.security import validate_security_settings
from src.engine import DecisionService
from src.engine.artifact_sources import resolve_artifact_directory
from src.engine.schemas import EngineRequest
from src.storage.decision_repository import DecisionRepository, create_decision_repository


def create_lifespan(
    decision_service: DecisionService | None = None,
    decision_repository: DecisionRepository | None = None,
):
    @asynccontextmanager
    async def lifespan(app):
        from src.core.config import load_settings

        settings = load_settings()
        validate_security_settings(settings)
        app.state.settings = settings
        artifact_dir = resolve_artifact_directory(settings)
        app.state.artifact_dir = artifact_dir
        app.state.decision_service = decision_service or DecisionService.from_directory(artifact_dir)
        app.state.decision_repository = decision_repository or create_decision_repository(settings)
        yield

    return lifespan


def get_decision_service(request: Request) -> DecisionService:
    service = getattr(request.app.state, "decision_service", None)
    if service is None:
        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            from src.core.config import load_settings

            settings = load_settings()
            request.app.state.settings = settings
        artifact_dir = resolve_artifact_directory(settings)
        request.app.state.artifact_dir = artifact_dir
        service = DecisionService.from_directory(artifact_dir)
        request.app.state.decision_service = service
    return service


def get_decision_repository(request: Request) -> DecisionRepository:
    repository = getattr(request.app.state, "decision_repository", None)
    if repository is None:
        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            from src.core.config import load_settings

            settings = load_settings()
            request.app.state.settings = settings
        repository = create_decision_repository(settings)
        request.app.state.decision_repository = repository
    return repository


def get_request_context(request: Request) -> Request:
    return request


def to_engine_request(payload: DecisionRequest) -> EngineRequest:
    return EngineRequest(
        request_id=payload.request_id,
        customer_context=payload.customer_context.model_dump(exclude_none=True, mode="json"),
        eligible_offers=[offer.value for offer in payload.eligible_offers],
    )
