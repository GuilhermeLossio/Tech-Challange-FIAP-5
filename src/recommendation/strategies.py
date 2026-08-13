from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Protocol

from src.recommendation.models import Candidate, OutcomeStats, RecommendationEvidence

_BAND_SCORE = {
    None: 0.0,
    "none": 0.0,
    "low": 0.25,
    "medium": 0.5,
    "high": 0.75,
    "very_high": 1.0,
}


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    score: float
    confidence: str
    reason_codes: tuple[str, ...]


class RecommendationStrategy(Protocol):
    name: str

    def rank(
        self,
        candidates: tuple[Candidate, ...],
        context: dict[str, object],
        request_id: str,
    ) -> list[ScoredCandidate]: ...


def _stable_sort(items: list[ScoredCandidate]) -> list[ScoredCandidate]:
    return sorted(items, key=lambda item: (-item.score, item.candidate.candidate_id))


def _baseline_score(candidate: Candidate) -> float:
    popularity = _BAND_SCORE.get(candidate.popularity_band, 0.0)
    stock = _BAND_SCORE.get(candidate.stock_band, 0.0)
    return round((candidate.priority * 0.01) + popularity + (stock * 0.001), 6)


class DeterministicBaseline:
    name = "deterministic_baseline"

    def rank(
        self,
        candidates: tuple[Candidate, ...],
        context: dict[str, object],
        request_id: str,
    ) -> list[ScoredCandidate]:
        del context, request_id
        return _stable_sort(
            [
                ScoredCandidate(
                    candidate=candidate,
                    score=_baseline_score(candidate),
                    confidence="deterministic",
                    reason_codes=("business_priority", "stable_tiebreak"),
                )
                for candidate in candidates
            ]
        )


class ContentAffinityRanker:
    name = "content_affinity"

    def rank(
        self,
        candidates: tuple[Candidate, ...],
        context: dict[str, object],
        request_id: str,
    ) -> list[ScoredCandidate]:
        del request_id
        affinities = {
            str(value) for value in context.get("category_affinities", []) if value is not None
        }
        scored = []
        for candidate in candidates:
            affinity = 1.0 if candidate.category_id in affinities else 0.0
            scored.append(
                ScoredCandidate(
                    candidate=candidate,
                    score=round(affinity + (_baseline_score(candidate) * 0.01), 6),
                    confidence="medium" if affinity else "low",
                    reason_codes=("content_affinity",) if affinity else ("cold_start_popularity",),
                )
            )
        return _stable_sort(scored)


class LikelihoodRanker:
    name = "likelihood_ranker"

    def __init__(
        self,
        evidence: RecommendationEvidence | None = None,
        *,
        smoothing_alpha: float = 2.0,
        min_samples: int = 10,
    ) -> None:
        self.evidence = evidence or RecommendationEvidence()
        self.smoothing_alpha = smoothing_alpha
        self.min_samples = min_samples

    def rank(
        self,
        candidates: tuple[Candidate, ...],
        context: dict[str, object],
        request_id: str,
    ) -> list[ScoredCandidate]:
        del request_id
        return _stable_sort([self._score(candidate, context) for candidate in candidates])

    def _score(self, candidate: Candidate, context: dict[str, object]) -> ScoredCandidate:
        stats = None
        reason = "contextual_conversion_rate"
        for context_key, fallback_reason in _context_keys(candidate.candidate_id, context):
            stats = self.evidence.context_stats.get(context_key)
            if stats is not None:
                reason = fallback_reason
                break
        if stats is None:
            stats = self.evidence.candidate_stats.get(candidate.candidate_id)
            reason = "candidate_conversion_rate"
        if stats is None and candidate.category_id:
            stats = self.evidence.category_stats.get(candidate.category_id)
            reason = "category_conversion_rate"
        if stats is None or stats.count == 0:
            affinities = {
                str(value) for value in context.get("category_affinities", []) if value is not None
            }
            if candidate.category_id and candidate.category_id in affinities:
                return ScoredCandidate(
                    candidate=candidate,
                    score=round(0.5 + (_baseline_score(candidate) * 0.001), 6),
                    confidence="low",
                    reason_codes=("content_affinity", "cold_start_fallback"),
                )
            if self.evidence.global_stats.count:
                global_rate = (
                    self.evidence.global_stats.successes / self.evidence.global_stats.count
                )
                return ScoredCandidate(
                    candidate=candidate,
                    score=round(global_rate, 6),
                    confidence="low",
                    reason_codes=("global_conversion_rate", "context_fallback"),
                )
            return ScoredCandidate(
                candidate=candidate,
                score=round(_baseline_score(candidate) * 0.001, 6),
                confidence="low",
                reason_codes=("global_conversion_rate", "cold_start_popularity"),
            )

        global_rate = (
            self.evidence.global_stats.successes / self.evidence.global_stats.count
            if self.evidence.global_stats.count
            else 0.0
        )
        score = (stats.successes + self.smoothing_alpha * global_rate) / (
            stats.count + self.smoothing_alpha
        )
        confidence = "high" if stats.count >= self.min_samples * 5 else "medium"
        if stats.count < self.min_samples:
            confidence = "low"
        return ScoredCandidate(
            candidate=candidate,
            score=round(score, 6),
            confidence=confidence,
            reason_codes=(reason,),
        )


class EpsilonGreedyRanker:
    name = "epsilon_greedy"

    def __init__(self, base: RecommendationStrategy, *, epsilon: float = 0.1) -> None:
        self.base = base
        self.epsilon = epsilon

    def rank(
        self,
        candidates: tuple[Candidate, ...],
        context: dict[str, object],
        request_id: str,
    ) -> list[ScoredCandidate]:
        ranked = self.base.rank(candidates, context, request_id)
        rng = random.Random(_seed(request_id, self.name))
        if len(ranked) > 1 and rng.random() < self.epsilon:
            chosen = rng.randrange(len(ranked))
            explored = ranked.pop(chosen)
            ranked.insert(
                0,
                ScoredCandidate(
                    candidate=explored.candidate,
                    score=explored.score,
                    confidence=explored.confidence,
                    reason_codes=(*explored.reason_codes, "exploration_epsilon"),
                ),
            )
        return ranked


class UCB1Ranker:
    name = "ucb"

    def __init__(self, evidence: RecommendationEvidence | None = None, *, confidence: float = 2.0) -> None:
        self.evidence = evidence or RecommendationEvidence()
        self.confidence = confidence

    def rank(
        self,
        candidates: tuple[Candidate, ...],
        context: dict[str, object],
        request_id: str,
    ) -> list[ScoredCandidate]:
        del context, request_id
        total = max(sum(stats.count for stats in self.evidence.candidate_stats.values()), 1)
        scored = []
        for candidate in candidates:
            stats = self.evidence.candidate_stats.get(candidate.candidate_id, OutcomeStats())
            mean = stats.successes / stats.count if stats.count else 0.0
            bonus = (
                math.sqrt(self.confidence * math.log(max(total, 2)) / stats.count)
                if stats.count
                else 10.0
            )
            scored.append(
                ScoredCandidate(
                    candidate=candidate,
                    score=round(mean + bonus, 6),
                    confidence="low" if stats.count < 10 else "medium",
                    reason_codes=("ucb_uncertainty",),
                )
            )
        return _stable_sort(scored)


class ThompsonSamplingRanker:
    name = "thompson_sampling"

    def __init__(
        self,
        evidence: RecommendationEvidence | None = None,
        *,
        alpha_prior: float = 1.0,
        beta_prior: float = 1.0,
    ) -> None:
        self.evidence = evidence or RecommendationEvidence()
        self.alpha_prior = alpha_prior
        self.beta_prior = beta_prior

    def rank(
        self,
        candidates: tuple[Candidate, ...],
        context: dict[str, object],
        request_id: str,
    ) -> list[ScoredCandidate]:
        del context
        rng = random.Random(_seed(request_id, self.name))
        scored = []
        for candidate in candidates:
            stats = self.evidence.candidate_stats.get(candidate.candidate_id, OutcomeStats())
            sample = rng.betavariate(
                self.alpha_prior + stats.successes,
                self.beta_prior + stats.failures,
            )
            scored.append(
                ScoredCandidate(
                    candidate=candidate,
                    score=round(sample, 6),
                    confidence="low" if stats.count < 10 else "medium",
                    reason_codes=("thompson_sample",),
                )
            )
        return _stable_sort(scored)


def _context_key(candidate_id: str, context: dict[str, object], fields: tuple[str, ...]) -> str:
    parts = [f"candidate={candidate_id}"]
    parts.extend(f"{field}={context[field]}" for field in fields if field in context)
    return "|".join(parts)


def _context_keys(
    candidate_id: str,
    context: dict[str, object],
) -> tuple[tuple[str, str], ...]:
    levels = (
        (
            ("channel", "newbie", "recency_band", "frequency_band", "history_segment"),
            "contextual_conversion_rate",
        ),
        (("channel", "history_segment", "newbie"), "reduced_context_conversion_rate"),
        (("channel", "history_segment"), "reduced_context_conversion_rate"),
        (("channel",), "channel_conversion_rate"),
    )
    keys: list[tuple[str, str]] = []
    for fields, reason in levels:
        if not all(field in context for field in fields):
            continue
        key = _context_key(candidate_id, context, fields)
        if key not in {existing for existing, _ in keys}:
            keys.append((key, reason))
    return tuple(keys)


def _seed(request_id: str, strategy: str) -> int:
    digest = hashlib.sha256(f"{request_id}:{strategy}".encode()).hexdigest()
    return int(digest[:16], 16)
