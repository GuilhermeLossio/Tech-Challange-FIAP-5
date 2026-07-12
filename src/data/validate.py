from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.config import load_settings
from src.data.schemas import ALLOWED_ACTIONS, BLOCKED_COLUMNS


def validate_dataset(df: pd.DataFrame) -> dict[str, Any]:
    errors: list[str] = []

    blocked_found = sorted(set(BLOCKED_COLUMNS).intersection(df.columns))
    if blocked_found:
        errors.append(f"Blocked columns found: {blocked_found}")

    if "action" not in df.columns:
        errors.append("Missing required processed column: action")
        invalid_actions: set[str] = set()
    else:
        invalid_actions = set(df["action"].dropna().unique()) - ALLOWED_ACTIONS
        if invalid_actions:
            errors.append(f"Invalid actions: {sorted(invalid_actions)}")

    if "reward" not in df.columns:
        errors.append("Missing required processed column: reward")
        invalid_rewards: set[int] = set()
    else:
        invalid_rewards = {
            reward.item() if hasattr(reward, "item") else reward
            for reward in set(df["reward"].dropna().unique()) - {0, 1}
        }
        if invalid_rewards:
            errors.append(f"Invalid rewards: {sorted(invalid_rewards)}")

    report = {
        "rows": len(df),
        "columns": len(df.columns),
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_values": df.isna().sum().to_dict(),
        "action_distribution": (
            df["action"].value_counts(normalize=True).to_dict()
            if "action" in df.columns
            else {}
        ),
        "conversion_rate": float(df["reward"].mean()) if "reward" in df.columns else None,
        "blocked_columns_found": blocked_found,
        "errors": errors,
        "valid": not errors,
    }

    return report


def write_validation_report(
    input_file: Path | None = None,
    output_file: Path | None = None,
) -> Path:
    settings = load_settings()
    source = input_file or settings.processed_file
    destination = output_file or settings.reports_dir / "data_validation.json"

    dataframe = pd.read_csv(source)
    report = validate_dataset(dataframe)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if not report["valid"]:
        raise ValueError(f"Dataset is invalid. See {destination}")

    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the processed Hillstrom dataset.")
    parser.add_argument("--input-file", type=Path, default=None, help="Processed CSV file.")
    parser.add_argument("--output-file", type=Path, default=None, help="Validation report path.")
    args = parser.parse_args()

    report_path = write_validation_report(
        input_file=args.input_file,
        output_file=args.output_file,
    )
    print(f"Validation report written to: {report_path}")


if __name__ == "__main__":
    main()
