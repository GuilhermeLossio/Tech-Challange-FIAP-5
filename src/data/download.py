from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from src.core.config import load_settings
from src.data.paths import ensure_data_dirs

KaggleApi: Any | None = None


def configure_kaggle_credentials() -> None:
    settings = load_settings()

    if settings.kaggle_username:
        os.environ.setdefault("KAGGLE_USERNAME", settings.kaggle_username)
    if settings.kaggle_key:
        os.environ.setdefault("KAGGLE_KEY", settings.kaggle_key)


def _select_downloaded_csv(target_dir: Path, expected_file: Path) -> Path:
    if expected_file.exists():
        return expected_file

    csv_files = sorted(target_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files were downloaded to {target_dir}")

    return csv_files[0]


def build_kaggle_api() -> Any:
    global KaggleApi

    if KaggleApi is None:
        from kaggle.api.kaggle_api_extended import KaggleApi as _KaggleApi

        KaggleApi = _KaggleApi

    return KaggleApi()


def download_dataset(dataset: str | None = None, output_dir: Path | None = None) -> Path:
    settings = load_settings()
    paths = ensure_data_dirs()

    dataset_slug = dataset or settings.kaggle_dataset
    target_dir = output_dir or paths["raw"]
    expected_file = target_dir / settings.raw_filename
    target_dir.mkdir(parents=True, exist_ok=True)

    configure_kaggle_credentials()

    api = build_kaggle_api()
    api.authenticate()
    api.dataset_download_files(dataset_slug, path=str(target_dir), unzip=True)

    downloaded_file = _select_downloaded_csv(target_dir, expected_file)
    if downloaded_file != expected_file:
        if expected_file.exists():
            expected_file.unlink()
        downloaded_file.rename(expected_file)

    return expected_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the Kaggle Hillstrom dataset.")
    parser.add_argument("--dataset", default=None, help="Kaggle dataset slug.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for raw files.")
    args = parser.parse_args()

    target_file = download_dataset(dataset=args.dataset, output_dir=args.output_dir)
    print(f"Dataset saved to: {target_file}")


if __name__ == "__main__":
    main()
