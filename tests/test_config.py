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
        "AZURE_STORAGE_ACCOUNT_URL",
        "AZURE_BLOB_CONTAINER_ARTIFACTS",
        "AZURE_ARTIFACT_PROMOTION_BLOB",
        "ARTIFACT_SOURCE",
        "ARTIFACT_CACHE_DIR",
        "ECLOE_PAY_DATABASE_MODE",
        "ECLOE_PAY_SQL_SERVER",
        "ECLOE_PAY_SQL_DATABASE",
        "ECLOE_PAY_SQL_AUTH_MODE",
        "ECLOE_PAY_SQL_DRIVER",
        "ECLOE_PAY_SESSION_TTL_SECONDS",
        "ECLOE_PAY_COOKIE_SECURE",
        "ECLOE_PAY_DEMO_USER_EMAIL",
        "ECLOE_PAY_DEMO_USER_PASSWORD",
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
    assert settings.artifact_source == "file"
    assert settings.azure_blob_container_artifacts == "ecloe-artifacts"
    assert settings.azure_artifact_promotion_blob == "promoted/current.json"
    assert settings.artifact_cache_dir == ROOT_DIR / ".artifact_cache"
    assert settings.ecloe_pay_database_mode == "memory"
    assert settings.ecloe_pay_sql_server == "ecloe-sql-1266.database.windows.net"
    assert settings.ecloe_pay_sql_database == "ecloe_validation"
    assert settings.ecloe_pay_sql_auth_mode == "entra_interactive"
    assert settings.ecloe_pay_cookie_secure is False


def test_config_rejects_unknown_ecloe_pay_database_mode(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "postgres")

    try:
        load_settings(use_env_file=False)
    except ValueError as error:
        assert "Unsupported ECLOE_PAY_DATABASE_MODE" in str(error)
    else:
        raise AssertionError("Expected invalid ECLOE_PAY_DATABASE_MODE to fail")


def test_config_requires_managed_identity_for_pay_sql_in_cloud(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "cloud")
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "azure_sql")
    monkeypatch.setenv("ECLOE_PAY_SQL_AUTH_MODE", "azure_cli")

    try:
        load_settings(use_env_file=False)
    except ValueError as error:
        assert "managed_identity" in str(error)
        assert "change-this-demo-password" not in str(error)
    else:
        raise AssertionError("Expected cloud ECloe Pay SQL auth validation to fail")
