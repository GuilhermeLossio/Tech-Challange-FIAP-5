from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv as _load_dotenv
except ModuleNotFoundError:
    _load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parents[2]
ECLOE_COSMOS_ACCOUNT = "ecloe5cosmos1266cl"
DEFAULT_AZURE_COSMOS_ENDPOINT = f"https://{ECLOE_COSMOS_ACCOUNT}.documents.azure.com:443/"
ECLOE_PAY_DATABASE_MODES = {"memory", "azure_sql"}
ECLOE_MARKET_DATABASE_MODES = {"memory", "azure_sql"}
ECLOE_PAY_SQL_AUTH_MODES = {"entra_interactive", "azure_cli", "managed_identity"}
CLOUD_ENVIRONMENTS = {"cloud", "prod", "production", "azure"}


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


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _bool_env(name: str, default: bool = False) -> bool:
    value = _env(name, str(default)).lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


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
    azure_storage_account_url: str
    azure_blob_container_raw: str
    azure_blob_container_processed: str
    azure_blob_container_artifacts: str
    azure_artifact_promotion_blob: str
    artifact_source: str
    artifact_cache_dir: Path
    azure_cosmos_endpoint: str
    azure_cosmos_key: str
    azure_cosmos_database: str
    azure_cosmos_container_decisions: str
    azure_cosmos_container_rewards: str
    azure_cosmos_container_policies: str
    app_environment: str
    api_host: str
    auth_mode: str
    entra_tenant_id: str
    entra_client_id: str
    entra_audience: str
    entra_issuer: str
    entra_jwks_url: str
    cors_allowed_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    max_payload_bytes: int
    max_concurrent_requests: int
    rate_limit_requests: int
    rate_limit_window_seconds: int
    azure_cosmos_auth_mode: str
    subject_key_salt: str
    decision_event_ttl_seconds: int
    decision_repository_mode: str
    decision_events_file: Path
    observability_enabled: bool
    applicationinsights_connection_string: str
    ecloe_pay_database_mode: str
    ecloe_pay_sql_server: str
    ecloe_pay_sql_database: str
    ecloe_pay_sql_auth_mode: str
    ecloe_pay_sql_driver: str
    ecloe_pay_session_ttl_seconds: int
    ecloe_pay_cookie_secure: bool
    ecloe_pay_demo_user_email: str
    ecloe_pay_demo_user_password: str
    ecloe_market_database_mode: str
    ecloe_market_catalog_path: Path
    ecloe_market_catalog_seed: int

    @property
    def raw_file(self) -> Path:
        return self.raw_data_dir / self.raw_filename

    @property
    def processed_file(self) -> Path:
        return self.processed_data_dir / self.processed_filename


def load_settings(*, use_env_file: bool = True, env_file: Path | None = None) -> Settings:
    if use_env_file:
        _load_env_file(env_file or ROOT_DIR / ".env")

    data_dir = ROOT_DIR / _env("DATA_DIR", "data")
    raw_data_dir = ROOT_DIR / _env("RAW_DATA_DIR", "data/raw")
    processed_data_dir = ROOT_DIR / _env("PROCESSED_DATA_DIR", "data/processed")
    reports_dir = ROOT_DIR / _env("REPORTS_DIR", "reports")

    settings = Settings(
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
        azure_storage_account_url=_env("AZURE_STORAGE_ACCOUNT_URL"),
        azure_blob_container_raw=_env("AZURE_BLOB_CONTAINER_RAW", "ecloe-raw"),
        azure_blob_container_processed=_env("AZURE_BLOB_CONTAINER_PROCESSED", "ecloe-processed"),
        azure_blob_container_artifacts=_env("AZURE_BLOB_CONTAINER_ARTIFACTS", "ecloe-artifacts"),
        azure_artifact_promotion_blob=_env(
            "AZURE_ARTIFACT_PROMOTION_BLOB",
            "promoted/current.json",
        ),
        artifact_source=_env("ARTIFACT_SOURCE", "file").lower(),
        artifact_cache_dir=ROOT_DIR / _env("ARTIFACT_CACHE_DIR", ".artifact_cache"),
        azure_cosmos_endpoint=_env("AZURE_COSMOS_ENDPOINT", DEFAULT_AZURE_COSMOS_ENDPOINT),
        azure_cosmos_key=_env("AZURE_COSMOS_KEY"),
        azure_cosmos_database=_env("AZURE_COSMOS_DATABASE", "ecloe"),
        azure_cosmos_container_decisions=_env("AZURE_COSMOS_CONTAINER_DECISIONS", "decisions"),
        azure_cosmos_container_rewards=_env("AZURE_COSMOS_CONTAINER_REWARDS", "rewards"),
        azure_cosmos_container_policies=_env("AZURE_COSMOS_CONTAINER_POLICIES", "policy_versions"),
        app_environment=_env("APP_ENVIRONMENT", "local").lower(),
        api_host=_env("API_HOST", "127.0.0.1"),
        auth_mode=_env("AUTH_MODE", "disabled").lower(),
        entra_tenant_id=_env("ENTRA_TENANT_ID"),
        entra_client_id=_env("ENTRA_CLIENT_ID"),
        entra_audience=_env("ENTRA_AUDIENCE") or _env("ENTRA_CLIENT_ID"),
        entra_issuer=_env("ENTRA_ISSUER"),
        entra_jwks_url=_env("ENTRA_JWKS_URL"),
        cors_allowed_origins=_split_csv(_env("CORS_ALLOWED_ORIGINS")),
        trusted_hosts=_split_csv(_env("TRUSTED_HOSTS", "127.0.0.1,localhost")),
        max_payload_bytes=int(_env("MAX_PAYLOAD_BYTES", "65536")),
        max_concurrent_requests=int(_env("MAX_CONCURRENT_REQUESTS", "16")),
        rate_limit_requests=int(_env("RATE_LIMIT_REQUESTS", "120")),
        rate_limit_window_seconds=int(_env("RATE_LIMIT_WINDOW_SECONDS", "60")),
        azure_cosmos_auth_mode=_env("AZURE_COSMOS_AUTH_MODE", "key").lower(),
        subject_key_salt=_env("SUBJECT_KEY_SALT", "local-dev-subject-key-salt"),
        decision_event_ttl_seconds=int(_env("DECISION_EVENT_TTL_SECONDS", "157680000")),
        decision_repository_mode=_env("DECISION_REPOSITORY_MODE", "file").lower(),
        decision_events_file=ROOT_DIR / _env("DECISION_EVENTS_FILE", "reports/decision_events.jsonl"),
        observability_enabled=_bool_env("OBSERVABILITY_ENABLED", True),
        applicationinsights_connection_string=_env("APPLICATIONINSIGHTS_CONNECTION_STRING"),
        ecloe_pay_database_mode=_env("ECLOE_PAY_DATABASE_MODE", "memory").lower(),
        ecloe_pay_sql_server=_env(
            "ECLOE_PAY_SQL_SERVER",
            "ecloe-sql-1266.database.windows.net",
        ),
        ecloe_pay_sql_database=_env("ECLOE_PAY_SQL_DATABASE", "ecloe_validation"),
        ecloe_pay_sql_auth_mode=_env("ECLOE_PAY_SQL_AUTH_MODE", "entra_interactive").lower(),
        ecloe_pay_sql_driver=_env("ECLOE_PAY_SQL_DRIVER", "ODBC Driver 18 for SQL Server"),
        ecloe_pay_session_ttl_seconds=int(_env("ECLOE_PAY_SESSION_TTL_SECONDS", "3600")),
        ecloe_pay_cookie_secure=_bool_env("ECLOE_PAY_COOKIE_SECURE", False),
        ecloe_pay_demo_user_email=_env(
            "ECLOE_PAY_DEMO_USER_EMAIL",
            _env("ECLOE_DEMO_USER_EMAIL", "demo.market@ecloe.local"),
        ),
        ecloe_pay_demo_user_password=_env(
            "ECLOE_PAY_DEMO_USER_PASSWORD",
            _env("ECLOE_DEMO_USER_PASSWORD", "change-this-demo-password"),
        ),
        ecloe_market_database_mode=_env("ECLOE_MARKET_DATABASE_MODE", "memory").lower(),
        ecloe_market_catalog_path=ROOT_DIR
        / _env("ECLOE_MARKET_CATALOG_PATH", "data/demo/ecloe_market_catalog.json"),
        ecloe_market_catalog_seed=int(_env("ECLOE_MARKET_CATALOG_SEED", "426")),
    )
    _validate_ecloe_pay_settings(settings)
    _validate_ecloe_market_settings(settings)
    return settings


def _validate_ecloe_pay_settings(settings: Settings) -> None:
    if settings.ecloe_pay_database_mode not in ECLOE_PAY_DATABASE_MODES:
        raise ValueError(f"Unsupported ECLOE_PAY_DATABASE_MODE: {settings.ecloe_pay_database_mode}")
    if settings.ecloe_pay_sql_auth_mode not in ECLOE_PAY_SQL_AUTH_MODES:
        raise ValueError(f"Unsupported ECLOE_PAY_SQL_AUTH_MODE: {settings.ecloe_pay_sql_auth_mode}")
    if settings.ecloe_pay_session_ttl_seconds <= 0:
        raise ValueError("ECLOE_PAY_SESSION_TTL_SECONDS must be greater than zero.")

    if settings.ecloe_pay_database_mode == "azure_sql":
        missing = []
        if not settings.ecloe_pay_sql_server:
            missing.append("ECLOE_PAY_SQL_SERVER")
        if not settings.ecloe_pay_sql_database:
            missing.append("ECLOE_PAY_SQL_DATABASE")
        if not settings.ecloe_pay_sql_driver:
            missing.append("ECLOE_PAY_SQL_DRIVER")
        if missing:
            raise ValueError(f"Missing ECloe Pay Azure SQL settings: {missing}")

    if settings.app_environment in CLOUD_ENVIRONMENTS:
        if settings.ecloe_pay_sql_auth_mode == "entra_interactive":
            raise ValueError("ECLOE_PAY_SQL_AUTH_MODE=entra_interactive is local-only.")
        if (
            settings.ecloe_pay_database_mode == "azure_sql"
            and settings.ecloe_pay_sql_auth_mode != "managed_identity"
        ):
            raise ValueError("Cloud ECloe Pay Azure SQL must use managed_identity.")


def _validate_ecloe_market_settings(settings: Settings) -> None:
    if settings.ecloe_market_database_mode not in ECLOE_MARKET_DATABASE_MODES:
        raise ValueError(f"Unsupported ECLOE_MARKET_DATABASE_MODE: {settings.ecloe_market_database_mode}")


settings = load_settings(use_env_file=False)
