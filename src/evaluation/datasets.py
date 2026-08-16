from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from src.recommendation.feedback import (
    TERMINAL_REWARDS,
    RecommendationFeedbackEvent,
    deduplicate_events,
)
from src.recommendation.models import Surface
from src.recommendation.privacy import COMMON_FEATURES, MARKET_FEATURES, PAY_FEATURES

ALLOWED_CONTEXT_FIELDS = {
    "market": (COMMON_FEATURES | MARKET_FEATURES) - {"surface", "decision_point"},
    "pay": (COMMON_FEATURES | PAY_FEATURES) - {"surface", "decision_point"},
}


@dataclass(frozen=True)
class BanditDatasetRow:
    """A privacy-minimized logged bandit observation.

    Technical identifiers are retained for lineage only and must not be used as
    model features.  A row exists only for terminal feedback that happened
    after its decision.
    """

    event_id: str
    decision_id: str
    surface: str
    decision_timestamp: str
    feedback_timestamp: str
    subject_key: str
    context: dict[str, Any]
    candidates: list[str]
    action: str
    reward: int
    behavior_policy: str
    behavior_policy_version: str
    behavior_propensity: float | None
    propensity_source: str
    candidate_propensities: dict[str, float]
    artifact_version: str
    artifact_checksum: str
    dataset_origin: str


def build_surface_dataset(
    decisions: Iterable[dict[str, Any]],
    events: Iterable[RecommendationFeedbackEvent],
    *,
    surface: Surface,
    origin: str = "observed",
) -> pd.DataFrame:
    """Build an independent Market or Pay causal-evaluation dataset."""

    if origin not in {"observed", "synthetic"}:
        raise ValueError("Dataset origin must be observed or synthetic.")
    decisions_by_id = {
        str(item.get("decision_id")): item
        for item in decisions
        if item.get("decision_id")
    }
    rows: list[BanditDatasetRow] = []
    for event in deduplicate_events(events):
        if event.surface is not surface:
            continue
        reward = TERMINAL_REWARDS[surface].get(event.event_type)
        if reward is None:
            continue
        decision = decisions_by_id.get(event.decision_id)
        if decision is None:
            continue
        decision_timestamp = _timestamp(
            decision.get("decision_timestamp", decision.get("created_at"))
        )
        if _parse_timestamp(event.occurred_at) < _parse_timestamp(decision_timestamp):
            continue
        context = _minimized_context(decision.get("minimized_context", decision.get("context", {})), surface)
        candidates = decision.get("eligible_candidate_ids") or decision.get("candidates") or []
        candidate_props = {
            str(key): float(value)
            for key, value in (
                event.candidate_propensities
                or decision.get("candidate_propensities")
                or {}
            ).items()
            if _valid_propensity(value)
        }
        rows.append(
            BanditDatasetRow(
                event_id=event.event_id,
                decision_id=event.decision_id,
                surface=surface.value,
                decision_timestamp=decision_timestamp,
                feedback_timestamp=event.occurred_at,
                subject_key=event.subject_key,
                context=context,
                candidates=[str(candidate) for candidate in candidates],
                action=event.candidate_id,
                reward=int(reward),
                behavior_policy=event.behavior_policy or str(decision.get("policy", "")),
                behavior_policy_version=event.behavior_policy_version
                or str(decision.get("policy_version", "")),
                behavior_propensity=_optional_propensity(
                    event.behavior_propensity
                    if event.behavior_propensity is not None
                    else decision.get("behavior_propensity")
                ),
                propensity_source=event.propensity_source
                or str(decision.get("propensity_source", "missing")),
                candidate_propensities=candidate_props,
                artifact_version=event.artifact_version
                or str(decision.get("artifact_version", "")),
                artifact_checksum=event.artifact_checksum
                or str(decision.get("artifact_checksum", "")),
                dataset_origin=origin,
            )
        )
    columns = list(BanditDatasetRow.__dataclass_fields__)
    return pd.DataFrame([asdict(row) for row in rows], columns=columns)


def build_market_offline_dataset(decisions: Iterable[dict[str, Any]], events: Iterable[RecommendationFeedbackEvent], **kwargs: Any) -> pd.DataFrame:
    return build_surface_dataset(decisions, events, surface=Surface.market, **kwargs)


def build_pay_offline_dataset(decisions: Iterable[dict[str, Any]], events: Iterable[RecommendationFeedbackEvent], **kwargs: Any) -> pd.DataFrame:
    return build_surface_dataset(decisions, events, surface=Surface.pay, **kwargs)


def causal_feature_columns(dataframe: pd.DataFrame) -> list[str]:
    """Return only permitted context fields, never lineage or identity fields."""

    return [
        field
        for field in sorted(ALLOWED_CONTEXT_FIELDS.get("market", set()) | ALLOWED_CONTEXT_FIELDS.get("pay", set()))
        if field in dataframe.columns
    ]


def serialize_dataset(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    result = dataframe.to_dict(orient="records")
    for row in result:
        for field in ("context", "candidates", "candidate_propensities"):
            if isinstance(row.get(field), (dict, list)):
                row[field] = json.dumps(row[field], sort_keys=True)
    return result


def _minimized_context(context: Any, surface: Surface) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    allowed = ALLOWED_CONTEXT_FIELDS.get(surface.value, set())
    return {key: value for key, value in context.items() if key in allowed}


def _timestamp(value: Any) -> str:
    if value is None:
        raise ValueError("Decision timestamp is required for causal evaluation.")
    return _parse_timestamp(value).isoformat()


def _parse_timestamp(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Dataset timestamps must include a timezone.")
    return parsed.astimezone(UTC)


def _valid_propensity(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return 0.0 < number <= 1.0 and number == number


def _optional_propensity(value: Any) -> float | None:
    return float(value) if _valid_propensity(value) else None
