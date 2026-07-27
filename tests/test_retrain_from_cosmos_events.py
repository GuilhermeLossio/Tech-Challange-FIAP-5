from __future__ import annotations

import json

from scripts.retrain_from_cosmos_events import retrain_from_events


def write_event_pair(source, index: int, reward: float) -> None:
    with source.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                {
                    "decision_id": f"dec_{index}",
                    "subject_key": "sub_1",
                    "request_id": f"req_{index}",
                    "selected_offer_id": "cashback_recurring_purchase",
                    "minimized_context": {
                        "channel": "Web",
                        "history_segment": "2) $100 - $200",
                        "newbie": index % 2,
                    },
                }
            )
            + "\n"
        )
        file.write(
            json.dumps(
                {
                    "record_type": "reward",
                    "decision_id": f"dec_{index}",
                    "subject_key": "sub_1",
                    "event_id": f"evt_{index}",
                    "event_type": "conversion" if reward > 0 else "dismissal",
                    "reward": reward,
                    "occurred_at": "2026-07-27T12:00:00Z",
                }
            )
            + "\n"
        )


def test_retrain_from_events_exports_and_runs_training(tmp_path) -> None:
    source = tmp_path / "decision_events.jsonl"
    export_file = tmp_path / "cosmos_training_events.csv"
    output_dir = tmp_path / "policy_training"
    for index, reward in enumerate([1.0, 0.0, 1.0, 0.0], start=1):
        write_event_pair(source, index, reward)

    result = retrain_from_events(
        export_file=export_file,
        output_dir=output_dir,
        source_jsonl=source,
        min_training_rows=2,
    )

    assert result["export"]["training_rows"] == 4
    assert result["training"]["train_rows"] == 2
    assert result["training"]["evaluation_rows"] == 2
    assert (output_dir / "selected_policy.json").exists()
    assert (output_dir / "purchase_likelihood_model.json").exists()


def test_retrain_from_events_rejects_zero_training_rows(tmp_path) -> None:
    source = tmp_path / "decision_events.jsonl"
    export_file = tmp_path / "cosmos_training_events.csv"
    output_dir = tmp_path / "policy_training"
    source.write_text("", encoding="utf-8")

    try:
        retrain_from_events(
            export_file=export_file,
            output_dir=output_dir,
            source_jsonl=source,
            min_training_rows=2,
        )
    except ValueError as error:
        assert "Not enough reusable decision/reward rows" in str(error)
    else:
        raise AssertionError("Expected empty export validation error")
