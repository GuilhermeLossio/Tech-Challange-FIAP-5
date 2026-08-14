from __future__ import annotations

import pytest

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
        "ECLOE_PAY_INITIAL_BALANCE_CENTS",
        "ECLOE_PAY_COOKIE_SECURE",
        "ECLOE_PAY_DEMO_USER_EMAIL",
        "ECLOE_PAY_DEMO_USER_PASSWORD",
        "ECLOE_WEB_AUTH_MODE",
        "ECLOE_WEB_ENTRA_AUTHORITY",
        "ECLOE_WEB_ENTRA_CLIENT_ID",
        "ECLOE_WEB_ENTRA_CLIENT_SECRET",
        "ECLOE_WEB_ENTRA_REDIRECT_URI",
        "ECLOE_WEB_ENTRA_POST_LOGOUT_REDIRECT_URI",
        "ECLOE_WEB_SESSION_IDLE_SECONDS",
        "ECLOE_WEB_OIDC_FLOW_TTL_SECONDS",
        "ECLOE_SIGNUP_MAX_ACCOUNTS_PER_IP",
        "ECLOE_SIGNUP_ADMIN_IP_ALLOWLIST",
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
    assert settings.ecloe_pay_demo_user_email == "demo.market@ecloe.local"
    assert settings.ecloe_pay_demo_user_password == "change-this-demo-password"
    assert settings.ecloe_pay_session_ttl_seconds == 28800
    assert settings.ecloe_pay_initial_balance_cents == 50000
    assert settings.ecloe_web_auth_mode == "local"
    assert settings.ecloe_web_session_idle_seconds == 1800
    assert settings.ecloe_web_oidc_flow_ttl_seconds == 600
    assert settings.ecloe_signup_max_accounts_per_ip == 1
    assert settings.ecloe_signup_admin_ip_allowlist == ()


def test_config_rejects_unknown_ecloe_pay_database_mode(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "postgres")

    with pytest.raises(ValueError, match="Unsupported ECLOE_PAY_DATABASE_MODE"):
        load_settings(use_env_file=False)


def test_config_rejects_unknown_web_auth_mode(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_WEB_AUTH_MODE", "password")

    with pytest.raises(ValueError, match="Unsupported ECLOE_WEB_AUTH_MODE"):
        load_settings(use_env_file=False)


def test_config_accepts_local_signup_web_auth_mode(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_WEB_AUTH_MODE", "local_signup")

    settings = load_settings(use_env_file=False)

    assert settings.ecloe_web_auth_mode == "local_signup"


def test_config_rejects_cloud_local_signup_without_azure_sql(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "cloud")
    monkeypatch.setenv("ECLOE_WEB_AUTH_MODE", "local_signup")
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "memory")

    with pytest.raises(ValueError, match="local_signup requires ECLOE_PAY_DATABASE_MODE=azure_sql"):
        load_settings(use_env_file=False)


def test_config_accepts_cloud_local_signup_with_azure_sql(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "cloud")
    monkeypatch.setenv("ECLOE_WEB_AUTH_MODE", "local_signup")
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "azure_sql")
    monkeypatch.setenv("ECLOE_PAY_SQL_AUTH_MODE", "managed_identity")

    settings = load_settings(use_env_file=False)

    assert settings.ecloe_web_auth_mode == "local_signup"


def test_config_requires_external_id_settings(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_WEB_AUTH_MODE", "entra_external")
    monkeypatch.setenv("ECLOE_WEB_ENTRA_AUTHORITY", "")
    monkeypatch.setenv("ECLOE_WEB_ENTRA_CLIENT_ID", "")
    monkeypatch.setenv("ECLOE_WEB_ENTRA_CLIENT_SECRET", "")

    with pytest.raises(ValueError, match="Missing ECloe web External ID settings"):
        load_settings(use_env_file=False)


def test_config_rejects_external_id_placeholder_settings(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_WEB_AUTH_MODE", "entra_external")
    monkeypatch.setenv("ECLOE_WEB_ENTRA_AUTHORITY", "https://seu-tenant.ciamlogin.com")
    monkeypatch.setenv("ECLOE_WEB_ENTRA_CLIENT_ID", "seu-client-id")
    monkeypatch.setenv("ECLOE_WEB_ENTRA_CLIENT_SECRET", "seu-client-secret")

    with pytest.raises(ValueError, match="placeholder values"):
        load_settings(use_env_file=False)


def test_config_rejects_unknown_ecloe_pay_sql_auth_mode(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_PAY_SQL_AUTH_MODE", "password")

    with pytest.raises(ValueError, match="Unsupported ECLOE_PAY_SQL_AUTH_MODE"):
        load_settings(use_env_file=False)


def test_config_rejects_non_positive_ecloe_pay_session_ttl(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_PAY_SESSION_TTL_SECONDS", "0")

    with pytest.raises(ValueError, match="ECLOE_PAY_SESSION_TTL_SECONDS"):
        load_settings(use_env_file=False)


def test_config_rejects_negative_initial_balance(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_PAY_INITIAL_BALANCE_CENTS", "-1")

    with pytest.raises(ValueError, match="ECLOE_PAY_INITIAL_BALANCE_CENTS"):
        load_settings(use_env_file=False)


def test_config_rejects_non_positive_signup_ip_limit(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_SIGNUP_MAX_ACCOUNTS_PER_IP", "0")

    with pytest.raises(ValueError, match="ECLOE_SIGNUP_MAX_ACCOUNTS_PER_IP"):
        load_settings(use_env_file=False)


def test_config_rejects_missing_azure_sql_settings_when_sql_mode_is_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "azure_sql")
    monkeypatch.setenv("ECLOE_PAY_SQL_SERVER", "")
    monkeypatch.setenv("ECLOE_PAY_SQL_DATABASE", "")
    monkeypatch.setenv("ECLOE_PAY_SQL_DRIVER", "")

    with pytest.raises(ValueError) as error:
        load_settings(use_env_file=False)

    message = str(error.value)
    assert "Missing ECloe Pay Azure SQL settings" in message
    assert "ECLOE_PAY_SQL_SERVER" in message
    assert "ECLOE_PAY_SQL_DATABASE" in message
    assert "ECLOE_PAY_SQL_DRIVER" in message


def test_config_rejects_entra_interactive_in_cloud(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "cloud")
    monkeypatch.setenv("ECLOE_WEB_AUTH_MODE", "local_signup")
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "azure_sql")
    monkeypatch.setenv("ECLOE_PAY_SQL_AUTH_MODE", "entra_interactive")

    with pytest.raises(ValueError, match="entra_interactive is local-only"):
        load_settings(use_env_file=False)


def test_config_requires_managed_identity_for_pay_sql_in_cloud(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "cloud")
    monkeypatch.setenv("ECLOE_WEB_AUTH_MODE", "local_signup")
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "azure_sql")
    monkeypatch.setenv("ECLOE_PAY_SQL_AUTH_MODE", "azure_cli")

    with pytest.raises(ValueError) as error:
        load_settings(use_env_file=False)

    assert "managed_identity" in str(error.value)
    assert "change-this-demo-password" not in str(error.value)
