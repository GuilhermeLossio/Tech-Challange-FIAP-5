from __future__ import annotations

import pandas as pd

from src.bandits import ACTIONS, DeterministicBaseline
from src.evaluation.causal import evaluate_logged_policy
from src.evaluation.datasets import build_market_offline_dataset
from src.evaluation.run import split_dataset_temporal
from src.recommendation.feedback import canonical_event


def test_doubly_robust_ips_and_snips_have_known_values() -> None:
    action = ACTIONS[0]
    frame = pd.DataFrame(
        {
            "row_id": ["1", "2", "3"],
            "action": [action, action, action],
            "reward": [1, 0, 1],
            "behavior_propensity": [0.5, 0.5, 0.5],
            "subject_key": ["a", "b", "a"],
        }
    )
    result = evaluate_logged_policy(
        DeterministicBaseline({item: (0.5 if item == action else 0.0) for item in ACTIONS}),
        frame,
        {item: (0.5 if item == action else 0.0) for item in ACTIONS},
        bootstrap_samples=20,
    )

    assert result.value == 5 / 6
    assert result.ips == 4 / 3
    assert result.snips == 2 / 3
    assert result.valid_rows == 3
    assert result.effective_sample_size == 3


def test_invalid_propensities_are_excluded_and_small_valid_values_are_clipped() -> None:
    action = ACTIONS[0]
    frame = pd.DataFrame(
        {
            "row_id": ["1", "2", "3"],
            "action": [action] * 3,
            "reward": [1, 1, 1],
            "behavior_propensity": [0.001, 0.0, None],
            "subject_key": ["a", "b", "c"],
        }
    )
    result = evaluate_logged_policy(
        DeterministicBaseline({item: (1.0 if item == action else 0.0) for item in ACTIONS}),
        frame,
        {action: 1.0},
        bootstrap_samples=10,
    )

    assert result.valid_rows == 1
    assert result.excluded_rows == 2
    assert result.clipped_rows == 1
    assert result.ips == 100.0


def test_temporal_split_sorts_and_keeps_70_15_15_boundaries() -> None:
    frame = pd.DataFrame(
        {
            "decision_timestamp": [f"2026-01-{day:02d}T00:00:00Z" for day in [10, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]],
            "row_id": list(range(20)),
        }
    )
    train, validation, test, boundaries = split_dataset_temporal(frame)

    assert (len(train), len(validation), len(test)) == (14, 3, 3)
    assert boundaries["method"] == "chronological_timestamp"
    assert train["decision_timestamp"].iloc[0].startswith("2026-01-01")
    assert train["decision_timestamp"].iloc[-1].startswith("2026-01-14")
    assert validation["decision_timestamp"].iloc[0].startswith("2026-01-15")


def test_market_dataset_maps_only_terminal_observed_feedback_and_strips_identity() -> None:
    decisions = [
        {
            "decision_id": "d1",
            "created_at": "2026-01-01T10:00:00Z",
            "selected_candidate_id": "product-1",
            "eligible_candidate_ids": ["product-1", "product-2"],
            "minimized_context": {"channel": "app", "email": "do-not-export"},
            "behavior_policy": "ranker",
            "behavior_policy_version": "v1",
            "behavior_propensity": 1.0,
        }
    ]
    events = [
        canonical_event(
            {
                "event_id": "e1",
                "decision_id": "d1",
                "surface": "market",
                "candidate_id": "product-1",
                "event_type": "purchase",
                "occurred_at": "2026-01-01T10:01:00Z",
                "subject_key": "subject-hash",
                "context": {"channel": "app"},
            }
        ),
        canonical_event(
            {
                "event_id": "e2",
                "decision_id": "d1",
                "surface": "market",
                "candidate_id": "product-1",
                "event_type": "click",
                "occurred_at": "2026-01-01T10:00:30Z",
                "subject_key": "subject-hash",
            }
        ),
    ]
    dataset = build_market_offline_dataset(decisions, events)

    assert len(dataset) == 1
    assert dataset.iloc[0]["reward"] == 1
    assert dataset.iloc[0]["context"] == {"channel": "app"}
    assert "email" not in dataset.iloc[0]["context"]
    assert dataset.iloc[0]["dataset_origin"] == "observed"
