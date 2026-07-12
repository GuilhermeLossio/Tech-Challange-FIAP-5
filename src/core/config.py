from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import os

try:
    from dotenv import load_dotenv as _load_dotenv
except ModuleNotFoundError:
    _load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path) -> None:
    if _load_dotenv is not None:
        _load_dotenv(path)
        return

    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    kaggle_dataset: str
    kaggle_username: str
    kaggle_key: str
    data_dir: Path
    raw_data_dir: Path
    processed_data_dir: Path
    reports_dir: Path
    raw_filename: str
    processed_filename: str
    random_seed: int
    azure_storage_connection_string: str
    azure_blob_container_raw: str
    azure_blob_container_processed: str
    azure_cosmos_endpoint: str
    azure_cosmos_key: str
    azure_cosmos_database: str
    azure_cosmos_container_decisions: str
    azure_cosmos_container_rewards: str
    azure_cosmos_container_policies: str

    @property
    def raw_file(self) -> Path:
        return self.raw_data_dir / self.raw_filename

    @property
    def processed_file(self) -> Path:
        return self.processed_data_dir / self.processed_filename


def load_settings() -> Settings:
    _load_env_file(ROOT_DIR / ".env")

    data_dir = ROOT_DIR / _env("DATA_DIR", "data")
    raw_data_dir = ROOT_DIR / _env("RAW_DATA_DIR", "data/raw")
    processed_data_dir = ROOT_DIR / _env("PROCESSED_DATA_DIR", "data/processed")
    reports_dir = ROOT_DIR / _env("REPORTS_DIR", "reports")

    return Settings(
        kaggle_dataset=_env(
            "KAGGLE_DATASET",
            "bofulee/kevin-hillstrom-minethatdata-e-mailanalytics",
        ),
        kaggle_username=_env("KAGGLE_USERNAME"),
        kaggle_key=_env("KAGGLE_KEY") or _env("KAGGLE_API_KEY"),
        data_dir=data_dir,
        raw_data_dir=raw_data_dir,
        processed_data_dir=processed_data_dir,
        reports_dir=reports_dir,
        raw_filename=_env("RAW_FILENAME", "hillstrom.csv"),
        processed_filename=_env("PROCESSED_FILENAME", "hillstrom_processed.csv"),
        random_seed=int(_env("RANDOM_SEED", "42")),
        azure_storage_connection_string=_env("AZURE_STORAGE_CONNECTION_STRING"),
        azure_blob_container_raw=_env("AZURE_BLOB_CONTAINER_RAW", "ecloe-raw"),
        azure_blob_container_processed=_env("AZURE_BLOB_CONTAINER_PROCESSED", "ecloe-processed"),
        azure_cosmos_endpoint=_env("AZURE_COSMOS_ENDPOINT"),
        azure_cosmos_key=_env("AZURE_COSMOS_KEY"),
        azure_cosmos_database=_env("AZURE_COSMOS_DATABASE", "ecloe"),
        azure_cosmos_container_decisions=_env("AZURE_COSMOS_CONTAINER_DECISIONS", "decisions"),
        azure_cosmos_container_rewards=_env("AZURE_COSMOS_CONTAINER_REWARDS", "rewards"),
        azure_cosmos_container_policies=_env("AZURE_COSMOS_CONTAINER_POLICIES", "policy_versions"),
    )


settings = load_settings()
