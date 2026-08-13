from __future__ import annotations

import pandas as pd

from src.data.validate import validate_dataset


def test_valid_dataset_passes_validation() -> None:
    dataframe = pd.DataFrame(
        {
            "action": ["legacy_variant_a", "legacy_variant_b", "legacy_control"],
            "reward": [1, 0, 0],
        }
    )

    report = validate_dataset(dataframe)

    assert report["valid"] is True
    assert report["errors"] == []


def test_blocked_column_fails_validation() -> None:
    dataframe = pd.DataFrame(
        {
            "customer_id": ["123"],
            "action": ["legacy_variant_a"],
            "reward": [1],
        }
    )

    report = validate_dataset(dataframe)

    assert report["valid"] is False
    assert report["blocked_columns_found"] == ["customer_id"]


def test_invalid_action_and_reward_fail_validation() -> None:
    dataframe = pd.DataFrame(
        {
            "action": ["invalid"],
            "reward": [2],
        }
    )

    report = validate_dataset(dataframe)

    assert report["valid"] is False
    assert "Invalid actions: ['invalid']" in report["errors"]
    assert "Invalid rewards: [2]" in report["errors"]
