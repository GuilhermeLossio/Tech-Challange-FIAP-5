from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EngineRequest:
    request_id: str
    customer_context: dict[str, Any]
    eligible_offers: list[str]


@dataclass(frozen=True)
class LikelihoodEstimate:
    offer_id: str
    proxy_action: str
    purchase_likelihood: float
    confidence: str
    fallback_level: str
    sample_count: int
    reason_codes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LikelihoodResponse:
    request_id: str
    estimates: list[LikelihoodEstimate]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DecisionResponse:
    request_id: str
    decision_id: str
    offer_id: str
    purchase_likelihood: float
    policy: str
    policy_version: str
    reason_codes: list[str]
    warnings: list[str] = field(default_factory=list)
