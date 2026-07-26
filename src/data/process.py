from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

from src.core.config import load_settings
from src.data.schemas import MODEL_CONTEXT_COLUMNS, REQUIRED_COLUMNS

ACTION_MAP = {
    "Mens E-Mail": "mens_email",
    "Womens E-Mail": "womens_email",
    "No E-Mail": "no_email",
}


def normalize_column_name(column: str) -> str:
    return column.strip().lower().replace(" ", "_").replace("-", "_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    processed = df.copy()
    processed.columns = [normalize_column_name(column) for column in processed.columns]
    return processed


def create_row_id(index: int) -> str:
    settings = load_settings()
    raw_value = f"ecloe-{settings.random_seed}-{index}"
    return hashlib.sha256(raw_value.encode()).hexdigest()[:16]


def process_dataset(df: pd.DataFrame) -> pd.DataFrame:
    processed = normalize_columns(df)

    missing_columns = set(REQUIRED_COLUMNS) - set(processed.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

    processed = processed.drop_duplicates().reset_index(drop=True)
    processed["action"] = processed["segment"].map(ACTION_MAP)

    if processed["action"].isna().any():
        invalid_actions = processed.loc[processed["action"].isna(), "segment"].unique()
        raise ValueError(f"Unknown campaign actions: {invalid_actions.tolist()}")

    processed["reward"] = processed["conversion"].astype(int).clip(lower=0, upper=1)
    processed["row_id"] = [create_row_id(index) for index in processed.index]

    selected_columns = [
        "row_id",
        *MODEL_CONTEXT_COLUMNS,
        "action",
        "reward",
        "visit",
        "spend",
    ]
    return processed[selected_columns]


def build_processed_dataset(input_file: Path | None = None, output_file: Path | None = None) -> Path:
    settings = load_settings()
    source = input_file or settings.raw_file
    destination = output_file or settings.processed_file

    dataframe = pd.read_csv(source)
    processed = process_dataset(dataframe)
    destination.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(destination, index=False)

    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Process the Hillstrom campaign dataset.")
    parser.add_argument("--input-file", type=Path, default=None, help="Raw Hillstrom CSV file.")
    parser.add_argument("--output-file", type=Path, default=None, help="Processed CSV file.")
    args = parser.parse_args()

    destination = build_processed_dataset(
        input_file=args.input_file,
        output_file=args.output_file,
    )
    print(f"Processed dataset written to: {destination}")


if __name__ == "__main__":
    main()
