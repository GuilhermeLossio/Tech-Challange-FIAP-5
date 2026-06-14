from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class DecisionEvent:
    customer_id: str
    offer_id: str
    policy_name: str
    policy_version: str
    context: dict[str, Any]
    reason_codes: list[str]
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "decision"
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def partition_key(self) -> str:
        return self.customer_id


@dataclass(frozen=True)
class RewardEvent:
    decision_id: str
    customer_id: str
    reward: int
    reward_type: str = "conversion"
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "reward"
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def partition_key(self) -> str:
        return self.customer_id


@dataclass(frozen=True)
class PolicyVersion:
    policy_name: str
    version: str
    status: str
    metrics: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "policy_version"
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def partition_key(self) -> str:
        return self.policy_name
