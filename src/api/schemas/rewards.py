from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator

from src.api.schemas.base import StrictApiModel


class RewardEventType(StrEnum):
    conversion = "conversion"
    click = "click"
    dismissal = "dismissal"


class RewardRequest(StrictApiModel):
    decision_id: str = Field(min_length=1, max_length=80)
    event_id: str = Field(min_length=1, max_length=128)
    event_type: RewardEventType
    reward: float = Field(ge=0.0, le=1.0)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class RewardResponse(StrictApiModel):
    decision_id: str
    event_id: str
    event_type: RewardEventType
    reward: float = Field(ge=0.0, le=1.0)
    occurred_at: str
    accepted: bool
