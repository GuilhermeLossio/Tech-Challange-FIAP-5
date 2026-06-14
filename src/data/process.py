from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.data.paths import ensure_data_dirs


TARGET_COLUMN = "y"
LEAKAGE_COLUMNS = ("duration",)


def find_bank_marketing_file(raw_dir: Path) -> Path:
    candidates = sorted(raw_dir.glob("*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No CSV files found in {raw_dir}")

    preferred = [
        file
        for file in candidates
        if file.name.lower() in {"bank-full.csv", "bank.csv", "bank-additional-full.csv"}
    ]
    return preferred[0] if preferred else candidates[0]


def read_bank_marketing_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=None, engine="python")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = (
        cleaned.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace(".", "_", regex=False)
    )
    return cleaned


def process_bank_marketing(df: pd.DataFrame) -> pd.DataFrame:
    processed = normalize_columns(df)

    for column in LEAKAGE_COLUMNS:
        if column in processed.columns:
            processed = processed.drop(columns=column)

    if TARGET_COLUMN not in processed.columns:
        raise KeyError(f"Expected target column '{TARGET_COLUMN}' was not found.")

    processed[TARGET_COLUMN] = (
        processed[TARGET_COLUMN]
        .astype(str)
        .str.strip()
        .str.lower()
        .map({"yes": 1, "no": 0})
    )

    if processed[TARGET_COLUMN].isna().any():
        raise ValueError("Target column contains values different from yes/no.")

    processed = processed.drop_duplicates().reset_index(drop=True)
    return processed


def build_processed_dataset(input_file: Path | None = None, output_file: Path | None = None) -> Path:
    paths = ensure_data_dirs()
    source = input_file or find_bank_marketing_file(paths["raw"])
    destination = output_file or paths["processed"] / "bank_marketing_processed.csv"

    df = read_bank_marketing_csv(source)
    processed = process_bank_marketing(df)
    destination.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(destination, index=False)

    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Process the Bank Marketing dataset.")
    parser.add_argument("--input-file", type=Path, default=None, help="Raw CSV file.")
    parser.add_argument("--output-file", type=Path, default=None, help="Processed CSV file.")
    args = parser.parse_args()

    destination = build_processed_dataset(
        input_file=args.input_file,
        output_file=args.output_file,
    )
    print(f"Processed dataset written to: {destination}")


if __name__ == "__main__":
    main()
