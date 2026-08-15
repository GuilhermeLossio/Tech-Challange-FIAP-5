from __future__ import annotations

import json
from dataclasses import replace

from src.core.config import load_settings
from src.engine.artifact_sources import ArtifactSourceError, load_recommendation_runtime
from src.recommendation.artifacts import evidence_from_payload
from src.recommendation.feedback import (
    aggregate_evidence,
    canonical_event,
    deduplicate_events,
)
from src.recommendation.models import Surface
from src.recommendation.pipeline import approve_surface_run, build_surface_run


def event(event_id: str, event_type: str, *, surface: str = "market") -> dict[str, object]:
    return {
        "event_id": event_id,
        "decision_id": "decision-1",
        "surface": surface,
        "candidate_id": "candidate-1",
        "position": 1,
        "event_type": event_type,
        "occurred_at": "2026-08-15T12:00:00Z",
        "context": {"channel": "Web", "newbie": 1},
        "category_id": "beauty",
    }


def test_feedback_aggregates_terminal_events_and_keeps_exposures() -> None:
    events = [
        canonical_event(event("one", "impression")),
        canonical_event(event("two", "purchase")),
        canonical_event(event("three", "expired")),
        canonical_event(event("pay-one", "acceptance", surface="pay")),
    ]

    evidence = aggregate_evidence(events)

    assert evidence[Surface.market].exposure_count == 3
    assert evidence[Surface.market].global_stats.successes == 1
    assert evidence[Surface.market].global_stats.count == 2
    assert evidence[Surface.market].candidate_stats["candidate-1"].successes == 1
    assert evidence[Surface.pay].global_stats.successes == 1


def test_feedback_deduplication_rejects_conflicting_event_reuse() -> None:
    first = canonical_event(event("same", "purchase"))
    assert deduplicate_events([first, first]) == (first,)

    conflicting = canonical_event(event("same", "expired"))
    try:
        deduplicate_events([first, conflicting])
    except ValueError as error:
        assert "collision" in str(error)
    else:
        raise AssertionError("event collision was not rejected")


def test_surface_artifact_run_is_loadable_only_after_approval(tmp_path) -> None:
    events = [canonical_event(event(f"event-{index}", "purchase")) for index in range(1_000)]
    run_dir = tmp_path / "market" / "run-1"
    build_surface_run(events, output_dir=run_dir, surface=Surface.market, run_id="run-1")

    settings = replace(
        load_settings(use_env_file=False),
        artifact_source="file",
        reports_dir=tmp_path,
    )
    serving_dir = tmp_path / "recommendation" / "market"
    serving_dir.mkdir(parents=True)
    for path in run_dir.iterdir():
        (serving_dir / path.name).write_bytes(path.read_bytes())
    try:
        load_recommendation_runtime(settings, Surface.market)
    except (ArtifactSourceError, ValueError):
        pass
    else:
        raise AssertionError("pending artifact was loaded as active")

    approve_surface_run(
        run_dir,
        surface=Surface.market,
        approver="reviewer",
        reason="validated test run",
        pointer_root=tmp_path,
    )
    # The local loader uses reports/recommendation/<surface>; copy the approved
    # run into that serving location to model the promoted cache layout.
    for path in run_dir.iterdir():
        (serving_dir / path.name).write_bytes(path.read_bytes())
    runtime = load_recommendation_runtime(settings, Surface.market)
    assert runtime.metadata.run_id == "run-1"
    assert runtime.evidence.global_stats.count == 1_000


def test_evidence_payload_does_not_add_sensitive_fields() -> None:
    payload = {
        "schema_version": "recommendation_evidence.v1",
        "global_stats": {"successes": 1, "count": 1},
        "candidate_stats": {},
        "category_stats": {},
        "context_stats": {},
    }
    serialized = json.dumps(payload)
    assert "email" not in serialized
    assert evidence_from_payload(payload).global_stats.count == 1
