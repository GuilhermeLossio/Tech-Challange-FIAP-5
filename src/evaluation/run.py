from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from src.bandits import ACTIONS, UCB1, DeterministicBaseline, EpsilonGreedy, ThompsonSampling
from src.bandits.policies import BanditPolicy
from src.data.legacy_hillstrom import normalize_legacy_action
from src.data.schemas import BLOCKED_COLUMNS
from src.engine.artifacts import ARTIFACT_STATUS_ACTIVE, SELECTED_POLICY_SCHEMA
from src.engine.likelihood import train_likelihood_model
from src.evaluation.causal import CausalEvaluation, evaluate_logged_policy, validate_propensity

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
    blocked_columns = sorted(set(BLOCKED_COLUMNS).intersection(df.columns))
    if blocked_columns:
        raise ValueError(f"Blocked columns in processed dataset: {blocked_columns}")

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


def split_dataset_temporal(
    dataframe: pd.DataFrame,
    *,
    train_ratio: float = 0.7,
    validation_ratio: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if len(dataframe) < 3:
        raise ValueError("Temporal evaluation requires at least 3 rows.")
    frame = dataframe.copy()
    split_method = "row_order_proxy"
    if "decision_timestamp" in frame.columns:
        parsed = pd.to_datetime(frame["decision_timestamp"], utc=True, errors="coerce")
        if parsed.notna().all():
            frame = frame.assign(_decision_timestamp=parsed).sort_values(
                "_decision_timestamp", kind="stable"
            )
            split_method = "chronological_timestamp"
    n_train = max(1, int(len(frame) * train_ratio))
    n_validation = max(n_train + 1, int(len(frame) * (train_ratio + validation_ratio)))
    n_validation = min(n_validation, len(frame) - 1)
    train = frame.iloc[:n_train].drop(columns=["_decision_timestamp"], errors="ignore")
    validation = frame.iloc[n_train:n_validation].drop(
        columns=["_decision_timestamp"], errors="ignore"
    )
    test = frame.iloc[n_validation:].drop(columns=["_decision_timestamp"], errors="ignore")
    boundaries = {
        "method": split_method,
        "train_rows": len(train),
        "validation_rows": len(validation),
        "test_rows": len(test),
    }
    if "decision_timestamp" in frame.columns:
        boundaries.update(
            {
                "train_start": str(train["decision_timestamp"].iloc[0]) if len(train) else None,
                "train_end": str(train["decision_timestamp"].iloc[-1]) if len(train) else None,
                "validation_start": str(validation["decision_timestamp"].iloc[0]) if len(validation) else None,
                "validation_end": str(validation["decision_timestamp"].iloc[-1]) if len(validation) else None,
                "test_start": str(test["decision_timestamp"].iloc[0]) if len(test) else None,
                "test_end": str(test["decision_timestamp"].iloc[-1]) if len(test) else None,
            }
        )
    return train.reset_index(drop=True), validation.reset_index(drop=True), test.reset_index(drop=True), boundaries


def train_reward_rates(train_df: pd.DataFrame) -> dict[str, float]:
    global_rate = float(train_df["reward"].mean()) if len(train_df) else 0.0
    rates: dict[str, float] = {}
    for action in ACTIONS:
        action_rewards = train_df.loc[train_df["action"] == action, "reward"]
        rates[action] = float(action_rewards.mean()) if len(action_rewards) else global_rate
    return rates


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
    reward_rates: dict[str, float],
    *,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    result: CausalEvaluation = evaluate_logged_policy(
        policy,
        evaluation_df,
        reward_rates,
        seed=seed,
    )
    return {
        "policy": policy.name,
        "rounds": len(evaluation_df),
        "dr_value": round(result.value, 6),
        "ips_value": round(result.ips, 6),
        "snips_value": round(result.snips, 6),
        "conversion_rate": round(result.observed_rate, 6),
        "support_rate": round(result.support_rate, 6),
        "valid_rows": result.valid_rows,
        "excluded_rows": result.excluded_rows,
        "clipped_rows": result.clipped_rows,
        "effective_sample_size": round(result.effective_sample_size, 6),
        "propensity_mean": result.propensity_mean,
        "confidence_interval": list(result.confidence_interval),
        "decisions": result.decisions,
        "state": policy.snapshot(),
    }


def select_policy(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not any(item["valid_rows"] for item in metrics):
        return next(item for item in metrics if item["policy"] == "baseline")
    return max(
        metrics,
        key=lambda item: (
            item["dr_value"] if item["valid_rows"] else float("-inf"),
            item["support_rate"],
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
        decision = decision_by_row.get(row.row_id, {})
        cases.append(
            {
                "case": case_number,
                "row_id": row.row_id,
                "context": {
                    "recency": getattr(row, "recency", None),
                    "history_segment": getattr(row, "history_segment", None),
                    "channel": getattr(row, "channel", None),
                    "newbie": getattr(row, "newbie", None),
                },
                "eligible_actions": list(ACTIONS),
                "recommended_action": decision.get(
                    "target_action", decision.get("selected_action", row.action)
                ),
                "policy": selected_policy,
                "reason_codes": [
                    "observed_offline" if decision else "unsupported_logged_row",
                    "policy_comparison_winner",
                ],
                "dataset_origin": "observed" if decision else "synthetic_demo",
                "split": "test",
            }
        )

    return cases


def write_outputs(
    output_dir: Path,
    metrics: list[dict[str, Any]],
    selected: dict[str, Any],
    reward_rates: dict[str, float],
    golden_set: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_summary = [
        {key: value for key, value in item.items() if key not in {"decisions", "state"}}
        for item in metrics
    ]

    (output_dir / "metrics.json").write_text(
        json.dumps(
            {
                **metadata,
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
            "dataset_origin": metadata.get("dataset_origin"),
            "evaluation_mode": metadata.get("evaluation_mode"),
            "estimator": metadata.get("estimator"),
            "propensity_method": metadata.get("propensity_method"),
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
                "schema_version": SELECTED_POLICY_SCHEMA,
                "artifact_status": (
                    ARTIFACT_STATUS_ACTIVE
                    if metadata.get("promotion_eligible") is True
                    else "pending_review"
                ),
                **metadata,
                "policy": selected["policy"],
                "version": "offline-v1",
                "selection_rule": "max validation doubly_robust value with support gate",
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
    if len(dataframe) < 2:
        raise ValueError("Training input must contain at least 2 rows.")
    if max_rows is not None:
        if max_rows < 2:
            raise ValueError("--max-rows must be at least 2")
        dataframe = dataframe.head(max_rows).copy()
    if "action" in dataframe.columns:
        dataframe["action"] = dataframe["action"].map(
            lambda value: normalize_legacy_action(str(value)) if pd.notna(value) else value
        )
    _validate_processed_dataset(dataframe)
    if "behavior_propensity" not in dataframe.columns:
        dataframe["behavior_propensity"] = float("nan")
    if "subject_key" not in dataframe.columns:
        dataframe["subject_key"] = dataframe["row_id"].astype(str)

    train_df, validation_df, test_df, split_metadata = split_dataset_temporal(dataframe)
    reward_rates = train_reward_rates(train_df)
    validation_metrics = [
        evaluate_policy(policy, validation_df, reward_rates, seed=seed)
        for policy in build_policies(reward_rates, seed)
    ]
    selected = select_policy(validation_metrics)
    selected_test = evaluate_policy(
        next(policy for policy in build_policies(reward_rates, seed) if policy.name == selected["policy"]),
        test_df,
        reward_rates,
        seed=seed,
    )
    metrics = [
        {
            **item,
            "validation": True,
            "test": item["policy"] == selected["policy"],
            "test_dr_value": selected_test["dr_value"] if item["policy"] == selected["policy"] else None,
            "test_ips_value": selected_test["ips_value"] if item["policy"] == selected["policy"] else None,
            "test_snips_value": selected_test["snips_value"] if item["policy"] == selected["policy"] else None,
            "test_support_rate": selected_test["support_rate"] if item["policy"] == selected["policy"] else None,
        }
        for item in validation_metrics
    ]
    selected_output = next(item for item in metrics if item["policy"] == selected["policy"])
    golden_set = build_golden_set(selected["policy"], test_df, {**selected_test, "decisions": selected_test["decisions"]})
    observed_rows = sum(
        validate_propensity(value) is not None
        for value in dataframe["behavior_propensity"].tolist()
    )
    metadata = {
        "dataset_origin": "observed" if observed_rows else "synthetic_demo",
        "evaluation_mode": "observed_offline" if observed_rows else "synthetic_demo",
        "estimator": "doubly_robust",
        "diagnostic_estimators": ["ips", "snips"],
        "propensity_method": "logged_behavior_propensity",
        "observed_row_count": observed_rows,
        "synthetic_row_count": len(dataframe) - observed_rows,
        "excluded_row_count": len(dataframe) - observed_rows,
        "split_boundaries": split_metadata,
        "promotion_eligible": bool(
            observed_rows
            and selected["valid_rows"] >= 1000
            and selected["support_rate"] > 0
            and split_metadata["method"] == "chronological_timestamp"
        ),
    }

    write_outputs(
        output_dir,
        metrics,
        selected_output,
        reward_rates,
        golden_set,
        metadata=metadata,
    )
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temporary:
        train_file = Path(temporary.name)
    try:
        train_df.to_csv(train_file, index=False)
        train_likelihood_model(input_file=train_file, output_file=output_dir / "purchase_likelihood_model.json")
    finally:
        train_file.unlink(missing_ok=True)

    return {
        "input_file": str(input_file),
        "output_dir": str(output_dir),
        "train_rows": len(train_df),
        "validation_rows": len(validation_df),
        "test_rows": len(test_df),
        "evaluation_rows": len(validation_df) + len(test_df),
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
