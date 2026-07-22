from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Channel(str, Enum):
    web = "Web"
    phone = "Phone"
    multichannel = "Multichannel"


class OfferId(str, Enum):
    mens_email = "mens_email"
    womens_email = "womens_email"
    no_email = "no_email"
    cashback_recurring_purchase = "cashback_recurring_purchase"
    savings_goal = "savings_goal"
    financial_education = "financial_education"
    account_upgrade = "account_upgrade"
    installment_education = "installment_education"
    credit_limit = "credit_limit"
    personal_loan = "personal_loan"
    cashback_investment = "cashback_investment"


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ReasonCode(str, Enum):
    contextual_conversion_rate = "contextual_conversion_rate"
    action_conversion_rate = "action_conversion_rate"
    context_fallback = "context_fallback"
    global_conversion_rate = "global_conversion_rate"
    action_fallback = "action_fallback"
    highest_validated_purchase_likelihood = "highest_validated_purchase_likelihood"


class ErrorCode(str, Enum):
    invalid_request = "invalid_request"
    artifact_unavailable = "artifact_unavailable"
    internal_error = "internal_error"


class CustomerContext(StrictApiModel):
    channel: Channel
    history_segment: str | None = Field(default=None, min_length=1, max_length=40)
    newbie: Literal[0, 1] | None = None


class DecisionRequest(StrictApiModel):
    request_id: str = Field(min_length=1, max_length=64)
    customer_context: CustomerContext
    eligible_offers: list[OfferId] = Field(min_length=1, max_length=10)

    @field_validator("eligible_offers")
    @classmethod
    def reject_duplicate_offers(cls, offers: list[OfferId]) -> list[OfferId]:
        values = [offer.value for offer in offers]
        if len(values) != len(set(values)):
            raise ValueError("eligible_offers must not contain duplicate offers")
        return offers


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


class DecisionResponse(StrictApiModel):
    request_id: str
    decision_id: str
    offer_id: OfferId
    purchase_likelihood: float = Field(ge=0.0, le=1.0)
    policy: Literal["likelihood_ranker", "thompson_sampling"]
    policy_version: str
    artifact_schema: str
    artifact_version: str
    artifact_checksum: str
    artifact_status: Literal["active"]
    reason_codes: list[ReasonCode]
    warnings: list[str]


class ArtifactResponse(StrictApiModel):
    artifact_schema: str = Field(alias="schema")
    version: str
    checksum: str
    status: Literal["active"]
    path: str


class PolicyResponse(StrictApiModel):
    policy: Literal["likelihood_ranker", "thompson_sampling"]
    version: str
    status: Literal["active"]
    artifact_schema: str
    artifact_version: str
    artifact_checksum: str
    artifact_status: Literal["active"]
    artifact_path: str
    promoted_offline_policy: dict[str, Any]
    promoted_offline_policy_artifact: ArtifactResponse


class HealthResponse(StrictApiModel):
    status: Literal["ok"]
    service: Literal["ecloe-engine"]


class ErrorResponse(StrictApiModel):
    code: ErrorCode
    message: str
