from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from src.api.dependencies import get_decision_service, to_engine_request
from src.api.errors import API_ERROR_RESPONSES, artifact_unavailable, invalid_request
from src.api.schemas.decisions import DecisionRequest
from src.api.schemas.likelihoods import PurchaseLikelihoodResponse
from src.engine import DecisionService
from src.engine.artifacts import ArtifactValidationError
from src.engine.validation import validate_engine_request


router = APIRouter(tags=["likelihoods"])


@router.post(
    "/v1/likelihood-estimates",
    response_model=PurchaseLikelihoodResponse,
    responses=API_ERROR_RESPONSES,
)
def likelihood_estimates(
    payload: DecisionRequest,
    service: DecisionService = Depends(get_decision_service),
) -> dict[str, object]:
    try:
        request = to_engine_request(payload)
        validate_engine_request(request)
        response = service.likelihood_service.estimate(request)
    except (ArtifactValidationError, FileNotFoundError) as error:
        raise artifact_unavailable(error) from error
    except ValueError as error:
        raise invalid_request(error) from error
    return asdict(response)


@router.post(
    "/v1/purchase-likelihood",
    response_model=PurchaseLikelihoodResponse,
    responses=API_ERROR_RESPONSES,
    deprecated=True,
)
def purchase_likelihood_alias(
    payload: DecisionRequest,
    service: DecisionService = Depends(get_decision_service),
) -> dict[str, object]:
    return likelihood_estimates(payload, service)
