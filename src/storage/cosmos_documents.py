from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class DecisionEvent:
    decision_id: str
    request_id: str
    subject_key: str
    selected_offer_id: str
    policy: str
    policy_version: str
    artifact_version: str
    artifact_checksum: str
    reason_codes: list[str]
    minimized_context: dict[str, Any]
    idempotency_key: str | None = None
    request_hash: str = ""
    ttl: int = 157680000
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "decision"
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def partition_key(self) -> str:
        return self.subject_key


@dataclass(frozen=True)
class RewardEvent:
    decision_id: str
    subject_key: str
    reward: int
    reward_type: str = "conversion"
    ttl: int = 157680000
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "reward"
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def partition_key(self) -> str:
        return self.subject_key


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
