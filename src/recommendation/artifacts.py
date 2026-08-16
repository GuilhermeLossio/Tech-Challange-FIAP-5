from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.recommendation.models import OutcomeStats, RecommendationEvidence, Surface

RECOMMENDATION_EVIDENCE_SCHEMA = "recommendation_evidence.v1"
RECOMMENDATION_ARTIFACT_SCHEMA = "recommendation_artifact.v1"


@dataclass(frozen=True)
class RecommendationArtifactMetadata:
    surface: Surface
    run_id: str
    version: str
    checksum: str
    status: str = "active"
    path: str = ""
    warning: str | None = None


@dataclass(frozen=True)
class RecommendationRuntime:
    evidence: RecommendationEvidence
    policy: str
    metadata: RecommendationArtifactMetadata


def evidence_from_payload(payload: dict[str, Any]) -> RecommendationEvidence:
    if payload.get("schema_version") != RECOMMENDATION_EVIDENCE_SCHEMA:
        raise ValueError("Unsupported recommendation evidence schema.")
    return RecommendationEvidence(
        global_stats=_stats(payload.get("global_stats")),
        candidate_stats=_stats_map(payload.get("candidate_stats")),
        category_stats=_stats_map(payload.get("category_stats")),
        context_stats=_stats_map(payload.get("context_stats")),
        exposure_count=_non_negative_int(payload.get("exposure_count", 0)),
        terminal_count=_non_negative_int(payload.get("terminal_count", 0)),
        positive_count=_non_negative_int(payload.get("positive_count", 0)),
    )


def evidence_to_payload(evidence: RecommendationEvidence) -> dict[str, Any]:
    return {
        "schema_version": RECOMMENDATION_EVIDENCE_SCHEMA,
        "global_stats": _stats_payload(evidence.global_stats),
        "candidate_stats": _stats_map_payload(evidence.candidate_stats),
        "category_stats": _stats_map_payload(evidence.category_stats),
        "context_stats": _stats_map_payload(evidence.context_stats),
        "exposure_count": evidence.exposure_count,
        "terminal_count": evidence.terminal_count,
        "positive_count": evidence.positive_count,
    }


def _stats(value: Any) -> OutcomeStats:
    if not isinstance(value, dict):
        raise ValueError("Recommendation evidence statistics must be objects.")
    successes = _non_negative_int(value.get("successes", 0))
    count = _non_negative_int(value.get("count", 0))
    if successes > count:
        raise ValueError("Recommendation evidence successes cannot exceed count.")
    return OutcomeStats(successes=successes, count=count)


def _stats_map(value: Any) -> dict[str, OutcomeStats]:
    if not isinstance(value, dict):
        raise ValueError("Recommendation evidence statistics map must be an object.")
    return {str(key): _stats(item) for key, item in value.items()}


def _stats_payload(value: OutcomeStats) -> dict[str, int]:
    return {"successes": value.successes, "count": value.count}


def _stats_map_payload(value: dict[str, OutcomeStats]) -> dict[str, dict[str, int]]:
    return {key: _stats_payload(item) for key, item in value.items()}


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Recommendation evidence counts must be non-negative integers.")
    return value
