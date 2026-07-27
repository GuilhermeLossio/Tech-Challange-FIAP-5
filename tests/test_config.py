from __future__ import annotations

from src.core.config import DEFAULT_AZURE_COSMOS_ENDPOINT, ROOT_DIR, load_settings


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
        "SUBJECT_KEY_SALT",
        "DECISION_EVENT_TTL_SECONDS",
        "DECISION_REPOSITORY_MODE",
        "DECISION_EVENTS_FILE",
        "OBSERVABILITY_ENABLED",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
    ]:
        monkeypatch.delenv(name, raising=False)

    settings = load_settings(use_env_file=False)

    assert settings.kaggle_dataset == "bofulee/kevin-hillstrom-minethatdata-e-mailanalytics"
    assert settings.raw_file == ROOT_DIR / "data" / "raw" / "hillstrom.csv"
    assert settings.processed_file == ROOT_DIR / "data" / "processed" / "hillstrom_processed.csv"
    assert settings.reports_dir == ROOT_DIR / "reports"
    assert settings.random_seed == 42
    assert settings.app_environment == "local"
    assert settings.api_host == "127.0.0.1"
    assert settings.auth_mode == "disabled"
    assert settings.azure_cosmos_auth_mode == "key"
    assert settings.azure_cosmos_endpoint == DEFAULT_AZURE_COSMOS_ENDPOINT
    assert settings.subject_key_salt == "local-dev-subject-key-salt"
    assert settings.decision_event_ttl_seconds == 157680000
    assert settings.decision_repository_mode == "file"
    assert settings.decision_events_file == ROOT_DIR / "reports" / "decision_events.jsonl"
    assert settings.observability_enabled is True
    assert settings.applicationinsights_connection_string == ""
