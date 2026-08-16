from __future__ import annotations

import pandas as pd
import pytest

from src.data.process import process_dataset


def hillstrom_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "recency": [2, 4, 3],
            "history_segment": ["1) Low", "2) Medium", "3) High"],
            "history": [50.0, 100.0, 200.0],
            "zip_code": ["Urban", "Rural", "Suburban"],
            "newbie": [1, 0, 0],
            "channel": ["Web", "Phone", "Multichannel"],
            "segment": ["Mens E-Mail", "Womens E-Mail", "No E-Mail"],
            "visit": [1, 0, 1],
            "conversion": [1, 0, 0],
            "spend": [50.0, 0.0, 0.0],
        }
    )


def test_process_dataset_creates_minimized_action_and_reward_columns() -> None:
    result = process_dataset(hillstrom_dataframe())

    assert result["action"].tolist() == [
        "legacy_variant_a",
        "legacy_variant_b",
        "legacy_control",
    ]
    assert result["reward"].tolist() == [1, 0, 0]
    assert result["row_id"].is_unique
    assert "history" not in result.columns
    assert "zip_code" not in result.columns
    assert result.columns.tolist() == [
        "row_id",
        "recency",
        "history_segment",
        "newbie",
        "channel",
        "action",
        "reward",
        "visit",
        "spend",
    ]


def test_process_dataset_rejects_unknown_segment() -> None:
    dataframe = hillstrom_dataframe()
    dataframe.loc[0, "segment"] = "Unknown"

    with pytest.raises(ValueError, match="Unknown campaign actions"):
        process_dataset(dataframe)


def test_process_dataset_rejects_missing_required_columns() -> None:
    dataframe = hillstrom_dataframe().drop(columns=["conversion"])

    with pytest.raises(ValueError, match="Missing required columns"):
        process_dataset(dataframe)
