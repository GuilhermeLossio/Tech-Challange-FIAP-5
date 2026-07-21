from __future__ import annotations

import json

import pandas as pd

from src.evaluation.run import run_evaluation


def processed_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": [f"row_{index}" for index in range(12)],
            "recency": [1, 2, 3, 4] * 3,
            "history_segment": ["1) Low", "2) Medium", "3) High"] * 4,
            "mens": [1, 0, 1, 0] * 3,
            "womens": [0, 1, 1, 0] * 3,
            "newbie": [1, 0, 0, 1] * 3,
            "channel": ["Web", "Phone", "Multichannel", "Web"] * 3,
            "action": ["mens_email", "womens_email", "no_email"] * 4,
            "reward": [1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 0, 0],
            "visit": [1, 0, 1, 1] * 3,
            "spend": [10.0, 0.0, 0.0, 20.0] * 3,
        }
    )


def test_run_evaluation_writes_expected_artifacts(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    output_dir = tmp_path / "policy_training"
    processed_dataframe().to_csv(input_file, index=False)

    result = run_evaluation(input_file=input_file, output_dir=output_dir, seed=42)

    assert result["selected_policy"]
    assert result["train_rows"] == 8
    assert result["evaluation_rows"] == 4

    expected_files = {
        "metrics.json",
        "metrics.csv",
        "policy_versions.json",
        "selected_policy.json",
        "golden_set_recommendations.json",
        "policy_state_thompson_sampling.json",
    }
    assert expected_files == {path.name for path in output_dir.iterdir()}

    metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert {item["policy"] for item in metrics["metrics"]} == {
        "baseline",
        "epsilon_greedy",
        "ucb",
        "thompson_sampling",
    }

    selected = json.loads((output_dir / "selected_policy.json").read_text(encoding="utf-8"))
    assert selected["policy"] in {
        "baseline",
        "epsilon_greedy",
        "ucb",
        "thompson_sampling",
    }


def test_run_evaluation_rejects_invalid_actions(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    output_dir = tmp_path / "policy_training"
    dataframe = processed_dataframe()
    dataframe.loc[0, "action"] = "invalid"
    dataframe.to_csv(input_file, index=False)

    try:
        run_evaluation(input_file=input_file, output_dir=output_dir, seed=42)
    except ValueError as error:
        assert "Invalid actions" in str(error)
    else:
        raise AssertionError("Expected invalid action validation error")


def test_run_evaluation_can_limit_rows_for_low_consumption(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    output_dir = tmp_path / "policy_training"
    processed_dataframe().to_csv(input_file, index=False)

    result = run_evaluation(input_file=input_file, output_dir=output_dir, seed=42, max_rows=6)

    assert result["max_rows"] == 6
    assert result["train_rows"] == 4
    assert result["evaluation_rows"] == 2


def test_run_evaluation_rejects_too_small_max_rows(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    output_dir = tmp_path / "policy_training"
    processed_dataframe().to_csv(input_file, index=False)

    try:
        run_evaluation(input_file=input_file, output_dir=output_dir, seed=42, max_rows=1)
    except ValueError as error:
        assert "--max-rows must be at least 2" in str(error)
    else:
        raise AssertionError("Expected max rows validation error")
