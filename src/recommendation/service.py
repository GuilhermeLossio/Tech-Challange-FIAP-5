from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from threading import RLock
from typing import TYPE_CHECKING
from uuid import uuid4

from src.recommendation.artifacts import RecommendationArtifactMetadata, RecommendationRuntime
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
        artifact_metadata_by_surface: dict[Surface, RecommendationArtifactMetadata] | None = None,
    ) -> None:
        self._lock = RLock()
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
        default_metadata = artifact_metadata_by_surface or {}
        self._runtime_by_surface = {
            surface: RecommendationRuntime(
                evidence=self.evidence_by_surface.get(surface, RecommendationEvidence()),
                policy=self.active_policy_by_surface[surface],
                metadata=self._metadata_with_guard_warning(
                    surface,
                    self.active_policy_by_surface[surface],
                    default_metadata.get(
                        surface,
                        RecommendationArtifactMetadata(
                            surface=surface,
                            run_id="baseline",
                            version=f"{surface.value}-baseline-v1",
                            checksum=self._evidence_checksum(surface),
                        ),
                    ),
                    requested=self.requested_policy_by_surface[surface],
                ),
            )
            for surface in (Surface.market, Surface.pay)
        }

    @classmethod
    def from_settings(cls, settings: Settings) -> RecommendationService:
        from src.engine.artifact_sources import load_recommendation_runtimes

        runtimes = load_recommendation_runtimes(settings)
        return cls(
            evidence_by_surface={surface: item.evidence for surface, item in runtimes.items()},
            active_policy_by_surface={surface: item.policy for surface, item in runtimes.items()},
            artifact_metadata_by_surface={
                surface: item.metadata for surface, item in runtimes.items()
            },
        )

    def decide(self, request: RecommendationRequest) -> RecommendationDecision:
        with self._lock:
            runtime = self._runtime_by_surface[request.surface]
        candidates = self._validated_candidates(request)
        policy_name = runtime.policy
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
            policy_version=runtime.metadata.version,
            artifact_schema=ARTIFACT_SCHEMA,
            artifact_version=runtime.metadata.version,
            artifact_checksum=runtime.metadata.checksum,
            artifact_status=runtime.metadata.status,
            warnings=self._warnings(request.surface, selected, runtime),
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
        with self._lock:
            runtime = self._runtime_by_surface[surface]
        policy = runtime.policy
        challengers = ["epsilon_greedy", "ucb", "thompson_sampling"]
        if policy == "deterministic_baseline":
            challengers.insert(0, "likelihood_ranker")
        return {
            "surface": surface.value,
            "policy": policy,
            "policy_version": runtime.metadata.version,
            "status": "active",
            "artifact_schema": ARTIFACT_SCHEMA,
            "artifact_version": runtime.metadata.version,
            "artifact_checksum": runtime.metadata.checksum,
            "challengers": challengers,
            "challenger_mode": "shadow",
            "promotion": "manual",
            "run_id": runtime.metadata.run_id,
            "warning": runtime.metadata.warning,
        }

    def reload(self, runtimes: dict[Surface, RecommendationRuntime]) -> dict[str, object]:
        with self._lock:
            next_runtime = dict(self._runtime_by_surface)
            for surface, runtime in runtimes.items():
                policy = self._guarded_policy_for_evidence(
                    surface, runtime.policy, runtime.evidence
                )
                next_runtime[surface] = RecommendationRuntime(
                    evidence=runtime.evidence,
                    policy=policy,
                    metadata=self._metadata_with_guard_warning(
                        surface, policy, runtime.metadata, requested=runtime.policy
                    ),
                )
            self._runtime_by_surface = next_runtime
            self.evidence_by_surface = {
                surface: runtime.evidence for surface, runtime in next_runtime.items()
            }
            self.active_policy_by_surface = {
                surface: runtime.policy for surface, runtime in next_runtime.items()
            }
        return {surface.value: self.current_policy(surface) for surface in runtimes}

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
        with self._lock:
            evidence = self._runtime_by_surface[surface].evidence
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
        runtime: RecommendationRuntime | None = None,
    ) -> tuple[str, ...]:
        warnings = []
        if self.requested_policy_by_surface[surface] != self.active_policy_by_surface[surface]:
            warnings.append("baseline_guardrail_active")
        if runtime and runtime.metadata.warning:
            warnings.append(runtime.metadata.warning)
        if all("cold_start_popularity" in item.reason_codes for item in selected):
            warnings.append("limited_evidence_fallback")
        return tuple(warnings)

    def _shadow_strategies(self, surface: Surface) -> dict[str, object]:
        with self._lock:
            evidence = self._runtime_by_surface[surface].evidence
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

    def _evidence_checksum(self, surface: Surface) -> str:
        return self._artifact_checksum(surface)

    def _guarded_policy_for_evidence(
        self, surface: Surface, policy: str, evidence: RecommendationEvidence
    ) -> str:
        if policy != "likelihood_ranker":
            return policy
        stats = evidence.global_stats
        if stats.count < MIN_PROMOTION_DECISIONS or stats.successes < MIN_PROMOTION_POSITIVES:
            return "deterministic_baseline"
        return policy

    def _metadata_with_guard_warning(
        self,
        surface: Surface,
        policy: str,
        metadata: RecommendationArtifactMetadata,
        *,
        requested: str | None = None,
    ) -> RecommendationArtifactMetadata:
        del surface
        if requested is not None and requested != policy and metadata.warning is None:
            return replace(metadata, warning="baseline_guardrail_active")
        return metadata
