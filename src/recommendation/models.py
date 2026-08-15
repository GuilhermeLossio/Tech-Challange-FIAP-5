from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Surface(StrEnum):
    market = "market"
    pay = "pay"


class CandidateType(StrEnum):
    product = "product"
    benefit = "benefit"


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    candidate_type: CandidateType
    available: bool = True
    category_id: str | None = None
    price_band: str | None = None
    stock_band: str | None = None
    popularity_band: str | None = None
    priority: int = 0
    benefit_type: str | None = None
    new_item: bool = False


@dataclass(frozen=True)
class RecommendationRequest:
    request_id: str
    surface: Surface
    decision_point: str
    context: dict[str, object]
    candidates: tuple[Candidate, ...]
    limit: int = 1


@dataclass(frozen=True)
class RankedCandidate:
    candidate_id: str
    candidate_type: CandidateType
    rank: int
    score: float
    confidence: str
    selection_probability: float
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RecommendationDecision:
    request_id: str
    decision_id: str
    surface: Surface
    decision_point: str
    created_at: str
    ranked_candidates: tuple[RankedCandidate, ...]
    policy: str
    policy_version: str
    artifact_schema: str
    artifact_version: str
    artifact_checksum: str
    artifact_status: str = "active"
    warnings: tuple[str, ...] = ()
    shadow_rankings: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OutcomeStats:
    successes: int = 0
    count: int = 0

    @property
    def failures(self) -> int:
        return max(self.count - self.successes, 0)


@dataclass(frozen=True)
class RecommendationEvidence:
    global_stats: OutcomeStats = OutcomeStats()
    candidate_stats: dict[str, OutcomeStats] = field(default_factory=dict)
    category_stats: dict[str, OutcomeStats] = field(default_factory=dict)
    context_stats: dict[str, OutcomeStats] = field(default_factory=dict)
    exposure_count: int = 0
    terminal_count: int = 0
    positive_count: int = 0
