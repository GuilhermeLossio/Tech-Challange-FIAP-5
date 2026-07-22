from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Header, Request

from src.api.dependencies import (
    get_decision_repository,
    get_decision_service,
    get_request_context,
    to_engine_request,
)
from src.api.errors import API_ERROR_RESPONSES, artifact_unavailable, invalid_request
from src.api.security import Principal, require_scopes, subject_key_for
from src.api.schemas.decisions import DecisionRequest, DecisionResponse
from src.core.config import Settings, load_settings
from src.engine import DecisionService
from src.engine.artifacts import ArtifactValidationError
from src.engine.validation import validate_engine_request
from src.storage.decision_repository import DecisionRecord, DecisionRepository, request_hash


router = APIRouter(prefix="/v1/decisions", tags=["decisions"])


@router.post("", response_model=DecisionResponse, responses=API_ERROR_RESPONSES)
def create_decision(
    payload: DecisionRequest,
    request_context: Request = Depends(get_request_context),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
    ),
    principal: Principal = Depends(require_scopes("decision:write")),
    service: DecisionService = Depends(get_decision_service),
    repository: DecisionRepository = Depends(get_decision_repository),
    settings: Settings = Depends(load_settings),
) -> dict[str, object]:
    try:
        subject_key = subject_key_for(principal, settings)
        if idempotency_key:
            existing = repository.get_by_idempotency_key(
                subject_key=subject_key,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                return existing.response

        request = to_engine_request(payload)
        validate_engine_request(request)
        response = service.decide(request)
        response_payload = asdict(response)
        saved = repository.save_decision(
            DecisionRecord(
                decision_id=response.decision_id,
                subject_key=subject_key,
                request_id=response.request_id,
                selected_offer_id=response.offer_id,
                policy=response.policy,
                policy_version=response.policy_version,
                artifact_version=response.artifact_version,
                artifact_checksum=response.artifact_checksum,
                reason_codes=response.reason_codes,
                created_at=response.created_at,
                minimized_context=request.customer_context,
                response=response_payload,
                idempotency_key=idempotency_key,
                request_hash=request_hash(
                    {
                        "request_id": request.request_id,
                        "customer_context": request.customer_context,
                        "eligible_offers": request.eligible_offers,
                    }
                ),
                ttl=settings.decision_event_ttl_seconds,
            )
        )
        if hasattr(request_context, "state"):
            request_context.state.decision_id = saved.decision_id
            request_context.state.policy_version = saved.policy_version
    except (ArtifactValidationError, FileNotFoundError) as error:
        raise artifact_unavailable(error) from error
    except ValueError as error:
        raise invalid_request(error) from error
    return saved.response
