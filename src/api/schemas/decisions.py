from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, field_validator

from src.api.schemas.base import StrictApiModel


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


class ReasonCode(str, Enum):
    contextual_conversion_rate = "contextual_conversion_rate"
    action_conversion_rate = "action_conversion_rate"
    context_fallback = "context_fallback"
    global_conversion_rate = "global_conversion_rate"
    action_fallback = "action_fallback"
    highest_validated_purchase_likelihood = "highest_validated_purchase_likelihood"


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


class DecisionResponse(StrictApiModel):
    request_id: str
    decision_id: str
    created_at: str
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
