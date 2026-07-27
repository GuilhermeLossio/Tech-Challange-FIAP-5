from __future__ import annotations

import csv
import json

from scripts.export_cosmos_events_for_training import build_training_rows, export_events


def test_build_training_rows_joins_decisions_and_rewards() -> None:
    decisions = [
        {
            "decision_id": "dec_1",
            "subject_key": "sub_1",
            "request_id": "req_1",
            "selected_offer_id": "cashback_recurring_purchase",
            "minimized_context": {
                "channel": "Web",
                "history_segment": "2) $100 - $200",
                "newbie": 0,
            },
        },
        {
            "decision_id": "dec_2",
            "subject_key": "sub_1",
            "request_id": "req_2",
            "selected_offer_id": "financial_education",
            "minimized_context": {"channel": "Phone", "newbie": 1},
        },
    ]
    rewards = [
        {
            "decision_id": "dec_1",
            "subject_key": "sub_1",
            "event_id": "evt_1",
            "event_type": "conversion",
            "reward": 1.0,
            "occurred_at": "2026-07-27T12:00:00Z",
        },
        {
            "decision_id": "dec_2",
            "subject_key": "sub_1",
            "event_id": "evt_2",
            "event_type": "dismissal",
            "reward": 0.0,
            "occurred_at": "2026-07-27T12:01:00Z",
        },
    ]

    rows = build_training_rows(decisions, rewards)

    assert rows == [
        {
            "row_id": "req_1",
            "recency": 0,
            "history_segment": "2) $100 - $200",
            "mens": 0,
            "womens": 1,
            "newbie": 0,
            "channel": "Web",
            "action": "womens_email",
            "reward": 1,
            "decision_id": "dec_1",
            "event_id": "evt_1",
            "occurred_at": "2026-07-27T12:00:00Z",
        },
        {
            "row_id": "req_2",
            "recency": 0,
            "history_segment": "unknown",
            "mens": 0,
            "womens": 0,
            "newbie": 1,
            "channel": "Phone",
            "action": "no_email",
            "reward": 0,
            "decision_id": "dec_2",
            "event_id": "evt_2",
            "occurred_at": "2026-07-27T12:01:00Z",
        },
    ]


def test_export_events_can_read_local_jsonl_fixture(tmp_path) -> None:
    source = tmp_path / "decision_events.jsonl"
    output = tmp_path / "cosmos_training_events.csv"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "decision_id": "dec_1",
                        "subject_key": "sub_1",
                        "request_id": "req_1",
                        "selected_offer_id": "savings_goal",
                        "minimized_context": {"channel": "Multichannel"},
                    }
                ),
                json.dumps(
                    {
                        "record_type": "reward",
                        "decision_id": "dec_1",
                        "subject_key": "sub_1",
                        "event_id": "evt_1",
                        "event_type": "conversion",
                        "reward": 1.0,
                        "occurred_at": "2026-07-27T12:00:00Z",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = export_events(output_file=output, source_jsonl=source)

    assert result["training_rows"] == 1
    with output.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["action"] == "mens_email"
    assert rows[0]["reward"] == "1"
