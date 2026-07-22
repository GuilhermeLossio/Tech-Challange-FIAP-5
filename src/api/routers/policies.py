from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_decision_service
from src.api.errors import API_ERROR_RESPONSES, artifact_unavailable
from src.api.schemas.policies import PolicyResponse
from src.engine import DecisionService
from src.engine.artifacts import ArtifactValidationError


router = APIRouter(prefix="/v1/policies", tags=["policies"])


@router.get("/current", response_model=PolicyResponse, responses=API_ERROR_RESPONSES)
def current_policy(service: DecisionService = Depends(get_decision_service)) -> dict[str, object]:
    try:
        return service.current_policy()
    except (ArtifactValidationError, FileNotFoundError) as error:
        raise artifact_unavailable(error) from error
