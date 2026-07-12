from __future__ import annotations

from src.core.config import ROOT_DIR, load_settings


def test_config_defaults_point_to_hillstrom_files(monkeypatch) -> None:
    for name in [
        "KAGGLE_DATASET",
        "RAW_FILENAME",
        "PROCESSED_FILENAME",
        "RANDOM_SEED",
        "DATA_DIR",
        "RAW_DATA_DIR",
        "PROCESSED_DATA_DIR",
        "REPORTS_DIR",
    ]:
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()

    assert settings.kaggle_dataset == "bofulee/kevin-hillstrom-minethatdata-e-mailanalytics"
    assert settings.raw_file == ROOT_DIR / "data" / "raw" / "hillstrom.csv"
    assert settings.processed_file == ROOT_DIR / "data" / "processed" / "hillstrom_processed.csv"
    assert settings.reports_dir == ROOT_DIR / "reports"
    assert settings.random_seed == 42
