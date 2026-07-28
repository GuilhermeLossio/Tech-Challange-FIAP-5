from __future__ import annotations

import os
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from werkzeug.security import generate_password_hash

from src.core.config import load_settings
from src.demo.ecloe_pay.repositories.base import initial_session, normalize_email, user_id_for_email

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "src" / "demo" / "ecloe_pay" / "schema.sql"
MIGRATION_ID = "20260728_ecloe_pay_azure_sql_schema"
PLACEHOLDER_PASSWORD = "change-this-demo-password"
SQL_TOKEN_SCOPE = "https://database.windows.net/.default"
REQUIRED_ODBC_DRIVER_FAMILY = "ODBC Driver 18"


@dataclass(frozen=True)
class InitSummary:
    connection_ok: bool
    schema_ok: bool
    migrations_applied: int
    persona_status: str
    seed_validation_ok: bool


def _require_explicit_demo_password() -> str:
    password = os.getenv("ECLOE_PAY_DEMO_USER_PASSWORD", "").strip()
    if not password:
        raise RuntimeError("ECLOE_PAY_DEMO_USER_PASSWORD must be set explicitly.")
    if password == PLACEHOLDER_PASSWORD:
        raise RuntimeError("ECLOE_PAY_DEMO_USER_PASSWORD must not use the placeholder value.")
    return password


def _validate_odbc_driver(driver_name: str) -> None:
    if REQUIRED_ODBC_DRIVER_FAMILY not in driver_name:
        raise RuntimeError("Microsoft ODBC Driver 18 for SQL Server is required.")
    try:
        import pyodbc
    except ModuleNotFoundError as error:
        raise RuntimeError("pyodbc is required. Install the azure-sql extra first.") from error

    available = set(pyodbc.drivers())
    if driver_name not in available:
        raise RuntimeError(f"{driver_name} was not found in installed ODBC drivers.")


def _entra_access_token(auth_mode: str) -> str:
    try:
        from azure.identity import (
            AzureCliCredential,
            InteractiveBrowserCredential,
            ManagedIdentityCredential,
        )
    except ModuleNotFoundError as error:
        raise RuntimeError("azure-identity is required. Install the azure-sql extra first.") from error

    if auth_mode == "azure_cli":
        credential = AzureCliCredential()
    elif auth_mode == "managed_identity":
        credential = ManagedIdentityCredential()
    elif auth_mode == "entra_interactive":
        credential = InteractiveBrowserCredential()
    else:
        raise RuntimeError(f"Unsupported ECLOE_PAY_SQL_AUTH_MODE: {auth_mode}")
    return credential.get_token(SQL_TOKEN_SCOPE).token


def _engine_with_entra_token(settings: Any, access_token: str) -> Any:
    try:
        from sqlalchemy import URL, create_engine
    except ModuleNotFoundError as error:
        raise RuntimeError("SQLAlchemy is required. Install the azure-sql extra first.") from error

    token_bytes = access_token.encode("utf-16-le")
    attrs_before = {1256: struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)}
    url = URL.create(
        "mssql+pyodbc",
        host=settings.ecloe_pay_sql_server,
        database=settings.ecloe_pay_sql_database,
        query={
            "driver": settings.ecloe_pay_sql_driver,
            "Encrypt": "yes",
            "TrustServerCertificate": "no",
            "Connection Timeout": "30",
        },
    )
    return create_engine(url, connect_args={"attrs_before": attrs_before}, pool_pre_ping=True)


def _schema_migration_applied(connection: Any) -> bool:
    from sqlalchemy import text

    exists = connection.execute(
        text("SELECT CASE WHEN OBJECT_ID(N'ecloe_pay.schema_migrations', N'U') IS NULL THEN 0 ELSE 1 END")
    ).scalar_one()
    if not exists:
        return False
    return bool(
        connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM ecloe_pay.schema_migrations
                WHERE migration_id = :migration_id
                """
            ),
            {"migration_id": MIGRATION_ID},
        ).scalar_one()
    )


def _apply_schema(connection: Any) -> int:
    before_applied = _schema_migration_applied(connection)
    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    for statement in re.split(r"(?im)^\s*GO\s*$", schema_sql):
        if statement.strip():
            connection.exec_driver_sql(statement)
    after_applied = _schema_migration_applied(connection)
    return int(after_applied and not before_applied)


def _create_or_update_persona(connection: Any, email: str, password_hash: str) -> tuple[str, str]:
    from sqlalchemy import text

    email_normalized = normalize_email(email)
    user_id = user_id_for_email(email_normalized)
    existed = bool(
        connection.execute(
            text("SELECT COUNT(*) FROM ecloe_pay.demo_users WHERE email_normalized = :email_normalized"),
            {"email_normalized": email_normalized},
        ).scalar_one()
    )
    connection.execute(
        text(
            """
            IF NOT EXISTS (
                SELECT 1 FROM ecloe_pay.demo_users WHERE email_normalized = :email_normalized
            )
            BEGIN
                INSERT INTO ecloe_pay.demo_users (
                    user_id, email_normalized, display_name, persona_label, password_hash,
                    is_active, is_demo, pii_allowed
                )
                VALUES (
                    :user_id, :email_normalized, N'ECloe Pay Demo Persona',
                    N'Synthetic wallet validation persona', :password_hash, 1, 1, 0
                )
            END
            ELSE
            BEGIN
                UPDATE ecloe_pay.demo_users
                SET password_hash = :password_hash,
                    display_name = N'ECloe Pay Demo Persona',
                    persona_label = N'Synthetic wallet validation persona',
                    is_active = 1,
                    is_demo = 1,
                    pii_allowed = 0,
                    updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                WHERE email_normalized = :email_normalized
            END
            """
        ),
        {"user_id": user_id, "email_normalized": email_normalized, "password_hash": password_hash},
    )
    return user_id, "updated" if existed else "created"


def _seed_deterministic_demo_state(connection: Any, user_id: str) -> None:
    from sqlalchemy import text

    session = initial_session(user_id)
    connection.execute(
        text(
            """
            IF NOT EXISTS (SELECT 1 FROM ecloe_pay.demo_sessions WHERE session_id = :session_id)
            BEGIN
                INSERT INTO ecloe_pay.demo_sessions (
                    session_id, user_id, demo_subject_key, selected_decision_id,
                    selected_offer_id, terms_accepted, expires_at
                )
                VALUES (
                    :session_id, :user_id, :demo_subject_key, :selected_decision_id,
                    :selected_offer_id, 0, DATEADD(hour, 4, TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00'))
                )
            END
            ELSE
            BEGIN
                UPDATE ecloe_pay.demo_sessions
                SET user_id = :user_id,
                    demo_subject_key = :demo_subject_key,
                    selected_decision_id = :selected_decision_id,
                    selected_offer_id = :selected_offer_id
                WHERE session_id = :session_id
            END
            """
        ),
        session.__dict__,
    )
    connection.execute(
        text(
            """
            IF NOT EXISTS (SELECT 1 FROM ecloe_pay.wallet_snapshots WHERE snapshot_id = N'snap_pay_demo_7841')
            BEGIN
                INSERT INTO ecloe_pay.wallet_snapshots (
                    snapshot_id, session_id, demo_balance_cents, cashback_cents,
                    savings_goal_percent, currency
                )
                VALUES (N'snap_pay_demo_7841', :session_id, 42870, 1840, 64, 'BRL')
            END
            """
        ),
        {"session_id": session.session_id},
    )
    connection.execute(
        text(
            """
            IF NOT EXISTS (
                SELECT 1 FROM ecloe_pay.payment_orders WHERE payment_order_id = :payment_order_id
            )
            BEGIN
                INSERT INTO ecloe_pay.payment_orders (
                    payment_order_id, session_id, market_order_id, amount_cents,
                    currency, status, idempotency_key
                )
                VALUES (
                    :payment_order_id, :session_id, :market_order_id, :payment_amount_cents,
                    'BRL', N'created', :idempotency_key
                )
            END
            ELSE
            BEGIN
                UPDATE ecloe_pay.payment_orders
                SET session_id = :session_id,
                    market_order_id = :market_order_id,
                    amount_cents = :payment_amount_cents,
                    currency = 'BRL',
                    updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                WHERE payment_order_id = :payment_order_id
            END
            """
        ),
        session.__dict__,
    )


def _validate_seed(connection: Any, email: str) -> bool:
    from sqlalchemy import text

    email_normalized = normalize_email(email)
    row = connection.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM ecloe_pay.demo_users
                 WHERE email_normalized = :email_normalized AND is_active = 1 AND is_demo = 1) AS users_count,
                (SELECT COUNT(*) FROM ecloe_pay.demo_sessions WHERE session_id LIKE N'sess_%') AS sessions_count,
                (SELECT COUNT(*) FROM ecloe_pay.wallet_snapshots
                 WHERE snapshot_id = N'snap_pay_demo_7841' AND currency = 'BRL') AS wallets_count,
                (SELECT COUNT(*) FROM ecloe_pay.payment_orders
                 WHERE payment_order_id = N'pay_order_demo_7841' AND currency = 'BRL') AS orders_count
            """
        ),
        {"email_normalized": email_normalized},
    ).mappings().one()
    return all(row[key] >= 1 for key in ("users_count", "sessions_count", "wallets_count", "orders_count"))


def initialize() -> InitSummary:
    password = _require_explicit_demo_password()
    settings = load_settings(use_env_file=False)
    _validate_odbc_driver(settings.ecloe_pay_sql_driver)
    access_token = _entra_access_token(settings.ecloe_pay_sql_auth_mode)
    engine = _engine_with_entra_token(settings, access_token)

    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            migrations_applied = _apply_schema(connection)
            password_hash = generate_password_hash(password)
            user_id, persona_status = _create_or_update_persona(
                connection,
                settings.ecloe_pay_demo_user_email,
                password_hash,
            )
            _seed_deterministic_demo_state(connection, user_id)
            seed_validation_ok = _validate_seed(connection, settings.ecloe_pay_demo_user_email)
        except Exception:
            transaction.rollback()
            raise
        else:
            transaction.commit()

    return InitSummary(
        connection_ok=True,
        schema_ok=True,
        migrations_applied=migrations_applied,
        persona_status=persona_status,
        seed_validation_ok=seed_validation_ok,
    )


def main() -> int:
    try:
        summary = initialize()
    except Exception as error:
        print(f"ECloe Pay SQL initialization failed: {type(error).__name__}", file=sys.stderr)
        return 1

    print(f"Azure SQL connection: {'OK' if summary.connection_ok else 'FAILED'}")
    print(f"Schema ecloe_pay: {'OK' if summary.schema_ok else 'FAILED'}")
    print(f"Migrations applied: {summary.migrations_applied}")
    print(f"Demo persona: {summary.persona_status}")
    print(f"Seed validation: {'OK' if summary.seed_validation_ok else 'FAILED'}")
    return 0 if summary.seed_validation_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
