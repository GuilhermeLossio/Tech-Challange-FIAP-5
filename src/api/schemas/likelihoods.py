from __future__ import annotations

from enum import Enum

from pydantic import Field

from src.api.schemas.base import StrictApiModel
from src.api.schemas.decisions import OfferId, ReasonCode


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class LikelihoodEstimateResponse(StrictApiModel):
    offer_id: OfferId
    proxy_action: OfferId
    purchase_likelihood: float = Field(ge=0.0, le=1.0)
    confidence: Confidence
    fallback_level: str
    sample_count: int = Field(ge=0)
    reason_codes: list[ReasonCode]
    warnings: list[str]


class PurchaseLikelihoodResponse(StrictApiModel):
    request_id: str
    estimates: list[LikelihoodEstimateResponse]
    warnings: list[str]
