from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_decision_service
from src.api.errors import API_ERROR_RESPONSES
from src.api.schemas.health import HealthResponse
from src.engine import DecisionService


router = APIRouter(tags=["health"])


@router.get("/livez", response_model=HealthResponse, responses=API_ERROR_RESPONSES)
def livez() -> dict[str, str]:
    return {"status": "ok", "service": "ecloe-engine"}


@router.get("/readyz", response_model=HealthResponse, responses=API_ERROR_RESPONSES)
def readyz(_: DecisionService = Depends(get_decision_service)) -> dict[str, str]:
    return {"status": "ready", "service": "ecloe-engine"}
