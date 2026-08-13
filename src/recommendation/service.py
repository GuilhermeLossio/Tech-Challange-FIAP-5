from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from src.recommendation.models import (
    Candidate,
    CandidateType,
    RankedCandidate,
    RecommendationDecision,
    RecommendationEvidence,
    RecommendationRequest,
    Surface,
)
from src.recommendation.privacy import assert_allowed_context, neutralize_category
from src.recommendation.strategies import (
    DeterministicBaseline,
    EpsilonGreedyRanker,
    LikelihoodRanker,
    ThompsonSamplingRanker,
    UCB1Ranker,
)

if TYPE_CHECKING:
    from src.core.config import Settings

ARTIFACT_SCHEMA = "recommendation_policy.v2"
MIN_PROMOTION_DECISIONS = 1_000
MIN_PROMOTION_POSITIVES = 100


class RecommendationService:
    def __init__(
        self,
        *,
        evidence_by_surface: dict[Surface, RecommendationEvidence] | None = None,
        active_policy_by_surface: dict[Surface, str] | None = None,
    ) -> None:
        self.evidence_by_surface = evidence_by_surface or {}
        defaults = {
            Surface.market: "deterministic_baseline",
            Surface.pay: "deterministic_baseline",
        }
        self.requested_policy_by_surface = {**defaults, **(active_policy_by_surface or {})}
        self.active_policy_by_surface = {
            surface: self._guarded_policy(surface, policy)
            for surface, policy in self.requested_policy_by_surface.items()
        }

    @classmethod
    def from_settings(cls, settings: Settings) -> RecommendationService:
        return cls(
            active_policy_by_surface={
                Surface.market: settings.recommendation_market_policy,
                Surface.pay: settings.recommendation_pay_policy,
            }
        )

    def decide(self, request: RecommendationRequest) -> RecommendationDecision:
        candidates = self._validated_candidates(request)
        policy_name = self.active_policy_by_surface[request.surface]
        strategy = self._strategy(policy_name, request.surface)
        ranked = strategy.rank(candidates, request.context, request.request_id)
        limit = min(max(request.limit, 1), 6 if request.surface is Surface.market else 1)
        selected = tuple(
            RankedCandidate(
                candidate_id=item.candidate.candidate_id,
                candidate_type=item.candidate.candidate_type,
                rank=index,
                score=item.score,
                confidence=item.confidence,
                selection_probability=1.0 if index == 1 else 0.0,
                reason_codes=item.reason_codes,
            )
            for index, item in enumerate(ranked[:limit], start=1)
        )
        shadow = {
            name: challenger.rank(candidates, request.context, request.request_id)[0].candidate.candidate_id
            for name, challenger in self._shadow_strategies(request.surface).items()
        }
        return RecommendationDecision(
            request_id=request.request_id,
            decision_id=f"dec_{uuid4()}",
            surface=request.surface,
            decision_point=request.decision_point,
            created_at=datetime.now(UTC).isoformat(),
            ranked_candidates=selected,
            policy=policy_name,
            policy_version="recommendation-v2",
            artifact_schema=ARTIFACT_SCHEMA,
            artifact_version=f"{request.surface.value}-recommendation-v2",
            artifact_checksum=self._artifact_checksum(request.surface),
            warnings=self._warnings(request.surface, selected),
            shadow_rankings=shadow,
        )

    def estimates(self, request: RecommendationRequest) -> tuple[RankedCandidate, ...]:
        candidates = self._validated_candidates(request)
        ranked = self._strategy("likelihood_ranker", request.surface).rank(
            candidates, request.context, request.request_id
        )
        return tuple(
            RankedCandidate(
                candidate_id=item.candidate.candidate_id,
                candidate_type=item.candidate.candidate_type,
                rank=index,
                score=item.score,
                confidence=item.confidence,
                selection_probability=0.0,
                reason_codes=item.reason_codes,
            )
            for index, item in enumerate(ranked, start=1)
        )

    def current_policy(self, surface: Surface) -> dict[str, object]:
        policy = self.active_policy_by_surface[surface]
        challengers = ["epsilon_greedy", "ucb", "thompson_sampling"]
        if policy == "deterministic_baseline":
            challengers.insert(0, "likelihood_ranker")
        return {
            "surface": surface.value,
            "policy": policy,
            "policy_version": "recommendation-v2",
            "status": "active",
            "artifact_schema": ARTIFACT_SCHEMA,
            "artifact_version": f"{surface.value}-recommendation-v2",
            "artifact_checksum": self._artifact_checksum(surface),
            "challengers": challengers,
            "challenger_mode": "shadow",
            "promotion": "manual",
        }

    def _validated_candidates(self, request: RecommendationRequest) -> tuple[Candidate, ...]:
        assert_allowed_context(request.context, request.surface.value)
        expected_type = CandidateType.product if request.surface is Surface.market else CandidateType.benefit
        filtered = tuple(
            candidate
            for candidate in request.candidates
            if candidate.candidate_type is expected_type
            and candidate.available
            and not (request.surface is Surface.market and candidate.stock_band == "none")
        )
        unsafe_categories = sorted(
            candidate.category_id
            for candidate in filtered
            if candidate.category_id
            and candidate.category_id != neutralize_category(candidate.category_id)
        )
        if unsafe_categories:
            raise ValueError(
                "Product categories must be normalized to neutral parent categories: "
                f"{unsafe_categories}"
            )
        if len({candidate.candidate_id for candidate in filtered}) != len(filtered):
            raise ValueError("eligible_candidates must not contain duplicate candidate_id values")
        if not filtered:
            raise ValueError("No eligible candidates are available for this decision")
        return filtered

    def _strategy(self, name: str, surface: Surface):
        evidence = self.evidence_by_surface.get(surface, RecommendationEvidence())
        if name == "deterministic_baseline":
            return DeterministicBaseline()
        if name == "likelihood_ranker":
            return LikelihoodRanker(evidence, smoothing_alpha=2.0, min_samples=10)
        raise ValueError(f"Unsupported active recommendation policy: {name}")

    def _guarded_policy(self, surface: Surface, policy: str) -> str:
        if policy != "likelihood_ranker":
            return policy
        stats = self.evidence_by_surface.get(surface, RecommendationEvidence()).global_stats
        if stats.count < MIN_PROMOTION_DECISIONS or stats.successes < MIN_PROMOTION_POSITIVES:
            return "deterministic_baseline"
        return policy

    def _warnings(
        self,
        surface: Surface,
        selected: tuple[RankedCandidate, ...],
    ) -> tuple[str, ...]:
        warnings = []
        if self.requested_policy_by_surface[surface] != self.active_policy_by_surface[surface]:
            warnings.append("baseline_guardrail_active")
        if all("cold_start_popularity" in item.reason_codes for item in selected):
            warnings.append("limited_evidence_fallback")
        return tuple(warnings)

    def _shadow_strategies(self, surface: Surface) -> dict[str, object]:
        evidence = self.evidence_by_surface.get(surface, RecommendationEvidence())
        likelihood = LikelihoodRanker(evidence, smoothing_alpha=2.0, min_samples=10)
        return {
            "epsilon_greedy": EpsilonGreedyRanker(likelihood, epsilon=0.1),
            "ucb": UCB1Ranker(evidence, confidence=2.0),
            "thompson_sampling": ThompsonSamplingRanker(evidence),
        }

    def _artifact_checksum(self, surface: Surface) -> str:
        evidence = asdict(self.evidence_by_surface.get(surface, RecommendationEvidence()))
        payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()
