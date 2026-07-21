from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
from typing import Any

import pandas as pd

from src.bandits import ACTIONS, DeterministicBaseline, EpsilonGreedy, ThompsonSampling, UCB1
from src.bandits.policies import BanditPolicy
from src.engine.likelihood import train_likelihood_model


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_FILE = ROOT_DIR / "data" / "processed" / "hillstrom_processed.csv"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "reports" / "policy_training"
DEFAULT_SEED = 42


def prepare_dataset() -> Path:
    from src.data.download import download_dataset
    from src.data.process import build_processed_dataset
    from src.data.validate import write_validation_report

    raw_file = download_dataset()
    processed_file = build_processed_dataset(input_file=raw_file)
    write_validation_report(input_file=processed_file)
    return processed_file


def _validate_processed_dataset(df: pd.DataFrame) -> None:
    required_columns = {"row_id", "action", "reward"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required processed columns: {sorted(missing)}")

    invalid_actions = sorted(set(df["action"].dropna().unique()) - set(ACTIONS))
    if invalid_actions:
        raise ValueError(f"Invalid actions in processed dataset: {invalid_actions}")

    invalid_rewards = sorted(set(df["reward"].dropna().unique()) - {0, 1})
    if invalid_rewards:
        raise ValueError(f"Invalid rewards in processed dataset: {invalid_rewards}")


def split_dataset(df: pd.DataFrame, train_ratio: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    split_index = max(1, min(len(df) - 1, int(len(df) * train_ratio)))
    return df.iloc[:split_index].reset_index(drop=True), df.iloc[split_index:].reset_index(drop=True)


def train_reward_rates(train_df: pd.DataFrame) -> dict[str, float]:
    global_rate = float(train_df["reward"].mean()) if len(train_df) else 0.0
    rates: dict[str, float] = {}
    for action in ACTIONS:
        action_rewards = train_df.loc[train_df["action"] == action, "reward"]
        rates[action] = float(action_rewards.mean()) if len(action_rewards) else global_rate
    return rates


def build_reward_table(
    evaluation_df: pd.DataFrame,
    reward_rates: dict[str, float],
    seed: int,
) -> list[dict[str, int]]:
    rng = random.Random(seed)
    table: list[dict[str, int]] = []
    for _ in evaluation_df.itertuples(index=False):
        table.append(
            {
                action: int(rng.random() < reward_rates[action])
                for action in ACTIONS
            }
        )
    return table


def build_policies(reward_rates: dict[str, float], seed: int) -> list[BanditPolicy]:
    return [
        DeterministicBaseline(reward_rates=reward_rates),
        EpsilonGreedy(epsilon=0.1, seed=seed),
        UCB1(confidence=2.0),
        ThompsonSampling(seed=seed),
    ]


def evaluate_policy(
    policy: BanditPolicy,
    evaluation_df: pd.DataFrame,
    reward_table: list[dict[str, int]],
    reward_rates: dict[str, float],
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    cumulative_reward = 0
    cumulative_regret = 0.0
    exploration_count = 0
    baseline_action = max(ACTIONS, key=lambda action: reward_rates[action])
    optimal_expected_reward = max(reward_rates.values())

    for index, row in enumerate(evaluation_df.itertuples(index=False)):
        action = policy.select_action()
        reward = reward_table[index][action]
        policy.update(action, reward)

        cumulative_reward += reward
        cumulative_regret += optimal_expected_reward - reward_rates[action]
        if action != baseline_action:
            exploration_count += 1

        decisions.append(
            {
                "row_id": getattr(row, "row_id"),
                "selected_action": action,
                "simulated_reward": reward,
                "cumulative_reward": cumulative_reward,
                "cumulative_regret": round(cumulative_regret, 6),
            }
        )

    total = len(evaluation_df)
    return {
        "policy": policy.name,
        "rounds": total,
        "cumulative_reward": cumulative_reward,
        "conversion_rate": round(cumulative_reward / total, 6) if total else 0.0,
        "cumulative_regret": round(cumulative_regret, 6),
        "exploration_rate": round(exploration_count / total, 6) if total else 0.0,
        "decisions": decisions,
        "state": policy.snapshot(),
    }


def select_policy(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        metrics,
        key=lambda item: (
            item["cumulative_reward"],
            -item["cumulative_regret"],
            -item["exploration_rate"],
            item["policy"] == "thompson_sampling",
        ),
    )


def build_golden_set(
    selected_policy: str,
    evaluation_df: pd.DataFrame,
    policy_result: dict[str, Any],
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    decision_by_row = {
        decision["row_id"]: decision
        for decision in policy_result["decisions"]
    }

    for case_number, row in enumerate(evaluation_df.head(5).itertuples(index=False), start=1):
        decision = decision_by_row[getattr(row, "row_id")]
        cases.append(
            {
                "case": case_number,
                "row_id": getattr(row, "row_id"),
                "context": {
                    "recency": getattr(row, "recency", None),
                    "history_segment": getattr(row, "history_segment", None),
                    "channel": getattr(row, "channel", None),
                    "newbie": getattr(row, "newbie", None),
                },
                "eligible_actions": list(ACTIONS),
                "recommended_action": decision["selected_action"],
                "policy": selected_policy,
                "reason_codes": ["offline_reward_evidence", "policy_comparison_winner"],
            }
        )

    return cases


def write_outputs(
    output_dir: Path,
    metrics: list[dict[str, Any]],
    selected: dict[str, Any],
    reward_rates: dict[str, float],
    golden_set: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_summary = [
        {key: value for key, value in item.items() if key not in {"decisions", "state"}}
        for item in metrics
    ]

    (output_dir / "metrics.json").write_text(
        json.dumps(
            {
                "reward_rates": reward_rates,
                "metrics": metrics_summary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with (output_dir / "metrics.csv").open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(metrics_summary[0].keys()))
        writer.writeheader()
        writer.writerows(metrics_summary)

    policy_versions = [
        {
            "policy_name": item["policy"],
            "version": "offline-v1",
            "status": "selected" if item["policy"] == selected["policy"] else "evaluated",
            "metrics": {key: item[key] for key in metrics_summary[0] if key != "policy"},
        }
        for item in metrics_summary
    ]
    (output_dir / "policy_versions.json").write_text(
        json.dumps(policy_versions, indent=2),
        encoding="utf-8",
    )

    (output_dir / "selected_policy.json").write_text(
        json.dumps(
            {
                "policy": selected["policy"],
                "version": "offline-v1",
                "selection_rule": "max cumulative_reward, then min cumulative_regret, then min exploration_rate",
                "metrics": {key: selected[key] for key in metrics_summary[0] if key != "policy"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (output_dir / "golden_set_recommendations.json").write_text(
        json.dumps(golden_set, indent=2),
        encoding="utf-8",
    )

    thompson = next(item for item in metrics if item["policy"] == "thompson_sampling")
    (output_dir / "policy_state_thompson_sampling.json").write_text(
        json.dumps(thompson["state"], indent=2),
        encoding="utf-8",
    )


def run_evaluation(
    input_file: Path = DEFAULT_INPUT_FILE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    seed: int = DEFAULT_SEED,
    max_rows: int | None = None,
) -> dict[str, Any]:
    dataframe = pd.read_csv(input_file)
    if max_rows is not None:
        if max_rows < 2:
            raise ValueError("--max-rows must be at least 2")
        dataframe = dataframe.head(max_rows).copy()
    _validate_processed_dataset(dataframe)

    train_df, evaluation_df = split_dataset(dataframe)
    reward_rates = train_reward_rates(train_df)
    reward_table = build_reward_table(evaluation_df, reward_rates, seed)

    metrics = [
        evaluate_policy(policy, evaluation_df, reward_table, reward_rates)
        for policy in build_policies(reward_rates, seed)
    ]
    selected = select_policy(metrics)
    golden_set = build_golden_set(selected["policy"], evaluation_df, selected)

    write_outputs(output_dir, metrics, selected, reward_rates, golden_set)
    train_likelihood_model(
        input_file=input_file,
        output_file=output_dir / "purchase_likelihood_model.json",
    )

    return {
        "input_file": str(input_file),
        "output_dir": str(output_dir),
        "train_rows": len(train_df),
        "evaluation_rows": len(evaluation_df),
        "max_rows": max_rows,
        "selected_policy": selected["policy"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline ECloe bandit policy evaluation.")
    parser.add_argument("--input-file", type=Path, default=DEFAULT_INPUT_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--prepare-data",
        action="store_true",
        help="Download, process, and validate the Hillstrom dataset before training.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Limit rows used by the local training run for low-consumption experiments.",
    )
    args = parser.parse_args()

    input_file = prepare_dataset() if args.prepare_data else args.input_file
    result = run_evaluation(
        input_file=input_file,
        output_dir=args.output_dir,
        seed=args.seed,
        max_rows=args.max_rows,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
