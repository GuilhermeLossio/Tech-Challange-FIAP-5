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
        "APP_ENVIRONMENT",
        "API_HOST",
        "AUTH_MODE",
        "TRUSTED_HOSTS",
        "AZURE_COSMOS_AUTH_MODE",
    ]:
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()

    assert settings.kaggle_dataset == "bofulee/kevin-hillstrom-minethatdata-e-mailanalytics"
    assert settings.raw_file == ROOT_DIR / "data" / "raw" / "hillstrom.csv"
    assert settings.processed_file == ROOT_DIR / "data" / "processed" / "hillstrom_processed.csv"
    assert settings.reports_dir == ROOT_DIR / "reports"
    assert settings.random_seed == 42
    assert settings.app_environment == "local"
    assert settings.api_host == "127.0.0.1"
    assert settings.auth_mode == "disabled"
    assert settings.azure_cosmos_auth_mode == "key"
