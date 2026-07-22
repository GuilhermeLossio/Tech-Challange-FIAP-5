from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from src.api.dependencies import get_decision_service, to_engine_request
from src.api.errors import API_ERROR_RESPONSES, artifact_unavailable, invalid_request
from src.api.schemas.decisions import DecisionRequest, DecisionResponse
from src.engine import DecisionService
from src.engine.artifacts import ArtifactValidationError
from src.engine.validation import validate_engine_request


router = APIRouter(prefix="/v1/decisions", tags=["decisions"])


@router.post("", response_model=DecisionResponse, responses=API_ERROR_RESPONSES)
def create_decision(
    payload: DecisionRequest,
    service: DecisionService = Depends(get_decision_service),
) -> dict[str, object]:
    try:
        request = to_engine_request(payload)
        validate_engine_request(request)
        response = service.decide(request)
    except (ArtifactValidationError, FileNotFoundError) as error:
        raise artifact_unavailable(error) from error
    except ValueError as error:
        raise invalid_request(error) from error
    return asdict(response)
