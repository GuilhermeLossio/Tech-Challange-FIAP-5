from __future__ import annotations

import argparse
import os
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

from src.core.config import load_settings
from src.data.paths import ensure_data_dirs


def configure_kaggle_credentials() -> None:
    settings = load_settings()

    if settings.kaggle_username:
        os.environ.setdefault("KAGGLE_USERNAME", settings.kaggle_username)
    if settings.kaggle_key:
        os.environ.setdefault("KAGGLE_KEY", settings.kaggle_key)


def download_dataset(dataset: str | None = None, output_dir: Path | None = None) -> Path:
    settings = load_settings()
    paths = ensure_data_dirs()

    dataset_slug = dataset or settings.kaggle_dataset
    target_dir = output_dir or paths["raw"]
    target_dir.mkdir(parents=True, exist_ok=True)

    configure_kaggle_credentials()

    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(dataset_slug, path=str(target_dir), unzip=True)

    downloaded_files = sorted(path for path in target_dir.iterdir() if path.is_file())
    if not downloaded_files:
        raise FileNotFoundError(f"No files were downloaded to {target_dir}")

    return target_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the Kaggle Bank Marketing dataset.")
    parser.add_argument("--dataset", default=None, help="Kaggle dataset slug.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for raw files.")
    args = parser.parse_args()

    target_dir = download_dataset(dataset=args.dataset, output_dir=args.output_dir)
    print(f"Dataset downloaded to: {target_dir}")


if __name__ == "__main__":
    main()
