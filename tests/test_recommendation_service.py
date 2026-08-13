from __future__ import annotations

import pytest

from src.recommendation import (
    Candidate,
    CandidateType,
    RecommendationRequest,
    RecommendationService,
    Surface,
)
from src.recommendation.models import OutcomeStats, RecommendationEvidence
from src.recommendation.strategies import (
    ContentAffinityRanker,
    EpsilonGreedyRanker,
    LikelihoodRanker,
    ThompsonSamplingRanker,
    UCB1Ranker,
)


def product(
    candidate_id: str,
    *,
    category: str = "beauty",
    stock: str = "high",
    priority: int = 0,
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        candidate_type=CandidateType.product,
        category_id=category,
        stock_band=stock,
        popularity_band="medium",
        priority=priority,
    )


def market_request(*candidates: Candidate, request_id: str = "req_market") -> RecommendationRequest:
    return RecommendationRequest(
        request_id=request_id,
        surface=Surface.market,
        decision_point="market_home",
        context={"channel": "Web", "newbie": 1},
        candidates=tuple(candidates),
        limit=6,
    )


def test_baseline_filters_inventory_and_uses_stable_tiebreak() -> None:
    service = RecommendationService()

    decision = service.decide(
        market_request(
            product("prd_b"),
            product("prd_unavailable", stock="none"),
            product("prd_a"),
        )
    )

    assert decision.policy == "deterministic_baseline"
    assert [item.candidate_id for item in decision.ranked_candidates] == ["prd_a", "prd_b"]
    assert all(item.candidate_id != "prd_unavailable" for item in decision.ranked_candidates)


def test_likelihood_policy_is_guarded_until_minimum_evidence() -> None:
    limited = RecommendationEvidence(global_stats=OutcomeStats(successes=99, count=999))
    promoted = RecommendationEvidence(global_stats=OutcomeStats(successes=100, count=1_000))

    guarded = RecommendationService(
        evidence_by_surface={Surface.market: limited},
        active_policy_by_surface={Surface.market: "likelihood_ranker"},
    )
    active = RecommendationService(
        evidence_by_surface={Surface.market: promoted},
        active_policy_by_surface={Surface.market: "likelihood_ranker"},
    )

    assert guarded.decide(market_request(product("prd_1"))).policy == "deterministic_baseline"
    assert "baseline_guardrail_active" in guarded.decide(
        market_request(product("prd_1"), request_id="req_guarded")
    ).warnings
    assert active.decide(market_request(product("prd_1"))).policy == "likelihood_ranker"


def test_likelihood_uses_reduced_context_then_candidate_category_global_and_content() -> None:
    reduced_key = "candidate=prd_context|channel=Web|history_segment=medium"
    evidence = RecommendationEvidence(
        global_stats=OutcomeStats(successes=200, count=1_000),
        context_stats={reduced_key: OutcomeStats(successes=8, count=10)},
        candidate_stats={"prd_candidate": OutcomeStats(successes=7, count=10)},
        category_stats={"home": OutcomeStats(successes=6, count=10)},
    )
    ranker = LikelihoodRanker(evidence)
    candidates = (
        product("prd_context"),
        product("prd_candidate"),
        product("prd_category", category="home"),
        product("prd_affinity", category="beauty"),
        product("prd_global", category="outdoors"),
    )

    ranked = ranker.rank(
        candidates,
        {
            "channel": "Web",
            "history_segment": "medium",
            "newbie": 0,
            "category_affinities": ["beauty"],
        },
        "req_hierarchy",
    )
    reasons = {item.candidate.candidate_id: item.reason_codes for item in ranked}

    assert reasons["prd_context"] == ("reduced_context_conversion_rate",)
    assert reasons["prd_candidate"] == ("candidate_conversion_rate",)
    assert reasons["prd_category"] == ("category_conversion_rate",)
    assert reasons["prd_affinity"] == ("content_affinity", "cold_start_fallback")
    assert reasons["prd_global"] == ("global_conversion_rate", "context_fallback")


def test_content_affinity_supports_anonymous_cold_start() -> None:
    ranked = ContentAffinityRanker().rank(
        (product("prd_other", category="home"), product("prd_match", category="beauty")),
        {"category_affinities": ["beauty"]},
        "req_anonymous",
    )

    assert ranked[0].candidate.candidate_id == "prd_match"
    assert ranked[0].reason_codes == ("content_affinity",)


def test_bandit_challengers_are_seeded_and_never_leave_eligible_candidates() -> None:
    candidates = (product("prd_a"), product("prd_b"), product("prd_c"))
    evidence = RecommendationEvidence(
        global_stats=OutcomeStats(successes=20, count=100),
        candidate_stats={
            "prd_a": OutcomeStats(successes=8, count=20),
            "prd_b": OutcomeStats(successes=3, count=10),
        },
    )
    base = LikelihoodRanker(evidence)
    strategies = (
        EpsilonGreedyRanker(base, epsilon=0.1),
        UCB1Ranker(evidence, confidence=2.0),
        ThompsonSamplingRanker(evidence),
    )

    for strategy in strategies:
        first = strategy.rank(candidates, {"channel": "Web"}, "req_seed_42")
        second = strategy.rank(candidates, {"channel": "Web"}, "req_seed_42")
        assert [item.candidate.candidate_id for item in first] == [
            item.candidate.candidate_id for item in second
        ]
        assert {item.candidate.candidate_id for item in first} == {
            candidate.candidate_id for candidate in candidates
        }


@pytest.mark.parametrize("blocked", ["sex", "gender", "email", "balance", "credit_score"])
def test_service_rejects_blocked_context_features(blocked: str) -> None:
    request = market_request(product("prd_1"))
    unsafe = RecommendationRequest(
        **{**request.__dict__, "context": {"channel": "Web", blocked: "blocked"}}
    )

    with pytest.raises(ValueError, match="Blocked decision feature"):
        RecommendationService().decide(unsafe)


def test_service_rejects_unknown_context_and_non_neutral_category() -> None:
    with pytest.raises(ValueError, match="non-allowlisted"):
        RecommendationService().decide(
            RecommendationRequest(
                **{
                    **market_request(product("prd_1")).__dict__,
                    "context": {"channel": "Web", "raw_navigation": ["prd_1"]},
                }
            )
        )

    with pytest.raises(ValueError, match="neutral parent categories"):
        RecommendationService().decide(market_request(product("prd_1", category="womens-shoes")))

