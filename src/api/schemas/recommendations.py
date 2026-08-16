from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from src.api.schemas.base import StrictApiModel
from src.api.schemas.decisions import Channel
from src.recommendation.models import CandidateType, Surface
from src.recommendation.privacy import neutralize_category


class MarketContext(StrictApiModel):
    channel: Channel
    newbie: Literal[0, 1] | None = None
    recency_band: str | None = Field(default=None, max_length=40)
    frequency_band: str | None = Field(default=None, max_length=40)
    history_segment: str | None = Field(default=None, max_length=40)
    category_affinities: list[str] = Field(default_factory=list, max_length=3)
    cart_size_band: str | None = Field(default=None, max_length=40)
    cart_value_band: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def normalize_affinities(self) -> MarketContext:
        self.category_affinities = [
            neutralize_category(category) for category in self.category_affinities
        ]
        return self


class PayContext(StrictApiModel):
    channel: Channel
    newbie: Literal[0, 1] | None = None
    recency_band: str | None = Field(default=None, max_length=40)
    frequency_band: str | None = Field(default=None, max_length=40)
    history_segment: str | None = Field(default=None, max_length=40)
    wallet_engagement_band: str | None = Field(default=None, max_length=40)
    benefit_response_band: str | None = Field(default=None, max_length=40)
    savings_goal_active: bool | None = None


class MarketCandidate(StrictApiModel):
    candidate_id: str = Field(min_length=1, max_length=80)
    candidate_type: Literal[CandidateType.product]
    available: bool = True
    category_id: str = Field(min_length=1, max_length=80)
    price_band: str = Field(min_length=1, max_length=40)
    stock_band: Literal["none", "low", "medium", "high", "very_high"]
    popularity_band: Literal["none", "low", "medium", "high", "very_high"] = "none"
    priority: int = Field(default=0, ge=0, le=100)
    new_item: bool = False

    @model_validator(mode="after")
    def normalize_category(self) -> MarketCandidate:
        self.category_id = neutralize_category(self.category_id)
        return self


class PayCandidate(StrictApiModel):
    candidate_id: str = Field(min_length=1, max_length=80)
    candidate_type: Literal[CandidateType.benefit]
    available: bool = True
    benefit_type: str = Field(min_length=1, max_length=80)
    priority: int = Field(default=0, ge=0, le=100)


CandidatePayload = Annotated[MarketCandidate | PayCandidate, Field(discriminator="candidate_type")]


class RecommendationRequestV2(StrictApiModel):
    request_id: str = Field(min_length=1, max_length=64)
    surface: Surface
    decision_point: str = Field(min_length=1, max_length=64)
    customer_context: MarketContext | PayContext
    eligible_candidates: list[CandidatePayload] = Field(min_length=1, max_length=50)
    limit: int = Field(default=1, ge=1, le=6)

    @model_validator(mode="after")
    def validate_surface_contract(self) -> RecommendationRequestV2:
        expected_context = MarketContext if self.surface is Surface.market else PayContext
        expected_candidate = CandidateType.product if self.surface is Surface.market else CandidateType.benefit
        maximum = 50 if self.surface is Surface.market else 10
        if not isinstance(self.customer_context, expected_context):
            raise ValueError(f"customer_context does not match surface={self.surface.value}")
        if len(self.eligible_candidates) > maximum:
            raise ValueError(f"surface={self.surface.value} accepts at most {maximum} candidates")
        if any(candidate.candidate_type is not expected_candidate for candidate in self.eligible_candidates):
            raise ValueError(f"eligible_candidates do not match surface={self.surface.value}")
        identifiers = [candidate.candidate_id for candidate in self.eligible_candidates]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("eligible_candidates must not contain duplicate candidate_id values")
        if self.surface is Surface.pay and self.limit != 1:
            raise ValueError("surface=pay returns exactly one eligible benefit")
        return self


class RankedCandidateResponse(StrictApiModel):
    candidate_id: str
    candidate_type: CandidateType
    rank: int = Field(ge=1)
    score: float = Field(ge=0.0)
    confidence: str
    selection_probability: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str]


class RecommendationDecisionResponse(StrictApiModel):
    request_id: str
    decision_id: str
    surface: Surface
    decision_point: str
    created_at: str
    ranked_candidates: list[RankedCandidateResponse]
    policy: str
    policy_version: str
    artifact_schema: str
    artifact_version: str
    artifact_checksum: str
    artifact_status: Literal["active"]
    warnings: list[str]


class LikelihoodEstimatesResponseV2(StrictApiModel):
    request_id: str
    surface: Surface
    estimates: list[RankedCandidateResponse]
    warnings: list[str]


class FeedbackRequestV2(StrictApiModel):
    decision_id: str = Field(min_length=1, max_length=80)
    event_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=80)
    position: int = Field(ge=1, le=20)
    event_type: Literal[
        "impression",
        "click",
        "open",
        "add_to_cart",
        "purchase",
        "acceptance",
        "dismissal",
        "rejection",
        "expired",
    ]
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value


class FeedbackResponseV2(StrictApiModel):
    decision_id: str
    event_id: str
    candidate_id: str
    position: int
    event_type: str
    occurred_at: str
    terminal: bool
    reward: float | None = Field(default=None, ge=0.0, le=1.0)
    recorded: Literal[True]


class RecommendationPolicyResponse(StrictApiModel):
    surface: Surface
    policy: str
    policy_version: str
    status: Literal["active"]
    artifact_schema: str
    artifact_version: str
    artifact_checksum: str
    challengers: list[str]
    challenger_mode: Literal["shadow"]
    promotion: Literal["manual"]
    run_id: str | None = None
    warning: str | None = None


class RecommendationReloadRequest(StrictApiModel):
    surface: Surface | Literal["all"] = "all"


class RecommendationReloadResponse(StrictApiModel):
    reloaded: dict[str, RecommendationPolicyResponse]
