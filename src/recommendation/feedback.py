from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.recommendation.artifacts import evidence_to_payload
from src.recommendation.models import OutcomeStats, RecommendationEvidence, Surface
from src.recommendation.privacy import assert_allowed_context


@dataclass(frozen=True)
class RecommendationFeedbackEvent:
    event_id: str
    decision_id: str
    surface: Surface
    candidate_id: str
    position: int
    event_type: str
    occurred_at: str
    subject_key: str = ""
    artifact_version: str = ""
    artifact_checksum: str = ""
    context: dict[str, Any] | None = None
    category_id: str | None = None


TERMINAL_REWARDS: dict[Surface, dict[str, int]] = {
    Surface.market: {"purchase": 1, "conversion": 1, "expired": 0},
    Surface.pay: {"acceptance": 1, "conversion": 1, "rejection": 0, "dismissal": 0, "expired": 0},
}


def canonical_event(payload: dict[str, Any]) -> RecommendationFeedbackEvent:
    surface = Surface(str(payload["surface"]))
    event = RecommendationFeedbackEvent(
        event_id=str(payload["event_id"]),
        decision_id=str(payload["decision_id"]),
        surface=surface,
        candidate_id=str(payload["candidate_id"]),
        position=int(payload.get("position", 1)),
        event_type=str(payload["event_type"]),
        occurred_at=_timestamp(payload["occurred_at"]),
        subject_key=str(payload.get("subject_key", "")),
        artifact_version=str(payload.get("artifact_version", "")),
        artifact_checksum=str(payload.get("artifact_checksum", "")),
        context=dict(payload.get("context") or {}),
        category_id=str(payload["category_id"]) if payload.get("category_id") else None,
    )
    if not event.event_id or not event.decision_id or not event.candidate_id:
        raise ValueError("Feedback event identifiers are required.")
    if event.position < 1:
        raise ValueError("Feedback position must be positive.")
    if event.context:
        assert_allowed_context(event.context, surface.value)
    return event


def adapt_engine_feedback(
    *,
    decision: dict[str, Any],
    feedback: dict[str, Any],
    subject_key: str = "",
) -> RecommendationFeedbackEvent:
    return canonical_event(
        {
            "event_id": feedback["event_id"],
            "decision_id": feedback["decision_id"],
            "surface": decision["surface"],
            "candidate_id": feedback["candidate_id"],
            "position": feedback["position"],
            "event_type": feedback["event_type"],
            "occurred_at": feedback["occurred_at"],
            "subject_key": subject_key,
            "artifact_version": decision.get("artifact_version", ""),
            "artifact_checksum": decision.get("artifact_checksum", ""),
            "context": decision.get("minimized_context", {}),
            "category_id": feedback.get("category_id"),
        }
    )


def adapt_market_feedback(payload: dict[str, Any]) -> RecommendationFeedbackEvent:
    return canonical_event({**payload, "surface": Surface.market.value})


def adapt_pay_feedback(payload: dict[str, Any]) -> RecommendationFeedbackEvent:
    return canonical_event({**payload, "surface": Surface.pay.value})


def events_from_engine_records(
    decisions: Iterable[dict[str, Any]], rewards: Iterable[dict[str, Any]]
) -> tuple[RecommendationFeedbackEvent, ...]:
    decisions_by_id = {
        str(item.get("decision_id")): item
        for item in decisions
        if item.get("decision_id")
    }
    events: list[RecommendationFeedbackEvent] = []
    for reward in rewards:
        decision = decisions_by_id.get(str(reward.get("decision_id")))
        if decision is None:
            continue
        candidate_id = (
            reward.get("candidate_id")
            or decision.get("selected_candidate_id")
            or decision.get("selected_offer_id")
        )
        if not candidate_id:
            continue
        events.append(
            canonical_event(
                {
                    "event_id": reward.get("event_id"),
                    "decision_id": reward.get("decision_id"),
                    "surface": decision.get("surface", Surface.pay.value),
                    "candidate_id": candidate_id,
                    "position": reward.get("position") or 1,
                    "event_type": reward.get("event_type"),
                    "occurred_at": reward.get("occurred_at"),
                    "subject_key": reward.get("subject_key", decision.get("subject_key", "")),
                    "artifact_version": decision.get("artifact_version", ""),
                    "artifact_checksum": decision.get("artifact_checksum", ""),
                    "context": decision.get("minimized_context", {}),
                    "category_id": reward.get("category_id"),
                }
            )
        )
    return deduplicate_events(events)


def deduplicate_events(events: Iterable[RecommendationFeedbackEvent]) -> tuple[RecommendationFeedbackEvent, ...]:
    unique: dict[str, RecommendationFeedbackEvent] = {}
    for event in events:
        previous = unique.get(event.event_id)
        if previous is not None and previous != event:
            raise ValueError(f"Feedback event_id collision: {event.event_id}")
        unique[event.event_id] = event
    return tuple(unique.values())


def aggregate_evidence(
    events: Iterable[RecommendationFeedbackEvent],
) -> dict[Surface, RecommendationEvidence]:
    grouped: dict[Surface, list[RecommendationFeedbackEvent]] = {Surface.market: [], Surface.pay: []}
    for event in deduplicate_events(events):
        grouped[event.surface].append(event)
    return {surface: _aggregate_surface(surface, items) for surface, items in grouped.items()}


def evidence_checksum(evidence: RecommendationEvidence) -> str:
    payload = json.dumps(evidence_to_payload(evidence), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _aggregate_surface(
    surface: Surface, events: list[RecommendationFeedbackEvent]
) -> RecommendationEvidence:
    global_successes = 0
    global_count = 0
    candidate: dict[str, list[int]] = {}
    category: dict[str, list[int]] = {}
    context: dict[str, list[int]] = {}
    terminal_count = 0
    positive_count = 0
    for event in events:
        reward = TERMINAL_REWARDS.get(surface, {}).get(event.event_type)
        if reward is None:
            continue
        terminal_count += 1
        positive_count += reward
        global_count += 1
        global_successes += reward
        _increment(candidate, event.candidate_id, reward)
        if event.category_id:
            _increment(category, event.category_id, reward)
        if event.context:
            key = _context_key(event.candidate_id, event.context)
            _increment(context, key, reward)
    return RecommendationEvidence(
        global_stats=OutcomeStats(successes=global_successes, count=global_count),
        candidate_stats=_stats_map(candidate),
        category_stats=_stats_map(category),
        context_stats=_stats_map(context),
        exposure_count=len(events),
        terminal_count=terminal_count,
        positive_count=positive_count,
    )


def _increment(target: dict[str, list[int]], key: str, reward: int) -> None:
    values = target.setdefault(key, [0, 0])
    values[0] += reward
    values[1] += 1


def _stats_map(values: dict[str, list[int]]) -> dict[str, OutcomeStats]:
    return {key: OutcomeStats(successes=item[0], count=item[1]) for key, item in values.items()}


def _context_key(candidate_id: str, context: dict[str, Any]) -> str:
    return "candidate=" + candidate_id + "|" + "|".join(
        f"{key}={context[key]}" for key in sorted(context)
    )


def _timestamp(value: Any) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Feedback timestamp must include a timezone.")
    return parsed.astimezone(UTC).isoformat()
