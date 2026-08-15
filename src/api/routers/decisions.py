from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from src.api.dependencies import (
    get_decision_repository,
    get_decision_service,
    get_request_context,
    to_engine_request,
)
from src.api.errors import (
    API_ERROR_RESPONSES,
    artifact_unavailable,
    idempotency_conflict,
    invalid_request,
)
from src.api.schemas.decisions import DecisionRequest, DecisionResponse
from src.api.security import Principal, require_scopes, subject_key_for
from src.core.config import Settings, load_settings
from src.engine import DecisionService
from src.engine.artifacts import ArtifactValidationError
from src.engine.validation import validate_engine_request
from src.storage.decision_repository import (
    DecisionRecord,
    DecisionRepository,
    IdempotencyConflict,
    request_hash,
)

router = APIRouter(prefix="/v1/decisions", tags=["decisions"])


@router.post("", response_model=DecisionResponse, responses=API_ERROR_RESPONSES)
def create_decision(
    payload: DecisionRequest,
    principal: Annotated[Principal, Depends(require_scopes("decision:write"))],
    service: Annotated[DecisionService, Depends(get_decision_service)],
    repository: Annotated[DecisionRepository, Depends(get_decision_repository)],
    settings: Annotated[Settings, Depends(load_settings)],
    request_context: Annotated[Request | None, Depends(get_request_context)] = None,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ] = None,
) -> dict[str, object]:
    try:
        subject_key = subject_key_for(principal, settings)
        request = to_engine_request(payload)
        validate_engine_request(request)
        payload_hash = request_hash(
            {
                "request_id": request.request_id,
                "customer_context": request.customer_context,
                "eligible_offers": request.eligible_offers,
            }
        )
        if idempotency_key:
            existing = repository.get_by_idempotency_key(
                subject_key=subject_key,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                if existing.request_hash and existing.request_hash != payload_hash:
                    raise IdempotencyConflict(
                        "Idempotency-Key was already used with a different request."
                    )
                return existing.response

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
                request_hash=payload_hash,
                ttl=settings.decision_event_ttl_seconds,
            )
        )
        if hasattr(request_context, "state"):
            request_context.state.decision_id = saved.decision_id
            request_context.state.policy_version = saved.policy_version
    except (ArtifactValidationError, FileNotFoundError) as error:
        raise artifact_unavailable(error) from error
    except IdempotencyConflict as error:
        raise idempotency_conflict(error) from error
    except ValueError as error:
        raise invalid_request(error) from error
    return saved.response
