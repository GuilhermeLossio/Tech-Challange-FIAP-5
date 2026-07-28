from __future__ import annotations

import hashlib
import os
import re
import struct
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "src" / "demo" / "ecloe_pay" / "schema.sql"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _require(name: str, default: str = "") -> str:
    value = _env(name, default)
    if not value:
        raise RuntimeError(f"{name} is required.")
    return value


def _user_id(email: str) -> str:
    digest = hashlib.sha256(_normalize_email(email).encode("utf-8")).hexdigest()[:24]
    return f"user_demo_{digest}"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _connection_url() -> tuple[str, dict[str, object]]:
    try:
        from sqlalchemy import URL
    except ModuleNotFoundError as error:
        raise RuntimeError("Install the azure-sql extra before running this script.") from error

    server = _require("ECLOE_PAY_SQL_SERVER", "ecloe-sql-1266.database.windows.net")
    database = _require("ECLOE_PAY_SQL_DATABASE", "ecloe_validation")
    driver = _require("ECLOE_PAY_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
    auth_mode = _require("ECLOE_PAY_SQL_AUTH_MODE", "azure_cli").lower()

    query = {
        "driver": driver,
        "Encrypt": "yes",
        "TrustServerCertificate": "no",
        "Connection Timeout": "30",
    }
    connect_args: dict[str, object] = {}
    if auth_mode == "entra_interactive":
        query["Authentication"] = "ActiveDirectoryInteractive"
    elif auth_mode == "azure_cli":
        try:
            from azure.identity import AzureCliCredential
        except ModuleNotFoundError as error:
            raise RuntimeError("azure-identity is required for ECLOE_PAY_SQL_AUTH_MODE=azure_cli.") from error
        token = AzureCliCredential().get_token("https://database.windows.net/.default").token
        token_bytes = token.encode("utf-16-le")
        connect_args["attrs_before"] = {1256: struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)}
    elif auth_mode == "managed_identity":
        query["Authentication"] = "ActiveDirectoryMsi"
    else:
        raise RuntimeError(f"Unsupported ECLOE_PAY_SQL_AUTH_MODE: {auth_mode}")

    return (
        URL.create(
            "mssql+pyodbc",
            host=server,
            database=database,
            query=query,
        ),
        connect_args,
    )


def main() -> int:
    try:
        from sqlalchemy import create_engine, text
    except ModuleNotFoundError as error:
        raise RuntimeError("Install the azure-sql extra before running this script.") from error

    url, connect_args = _connection_url()
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    email = _require("ECLOE_PAY_DEMO_USER_EMAIL", "demo.pay@ecloe.local")
    password = _require("ECLOE_PAY_DEMO_USER_PASSWORD")
    password_hash = generate_password_hash(password)
    email_normalized = _normalize_email(email)
    user_id = _user_id(email)

    with engine.begin() as connection:
        for statement in re.split(r"(?im)^\s*GO\s*$", schema_sql):
            if statement.strip():
                connection.exec_driver_sql(statement)
        connection.execute(
            text(
                """
                IF NOT EXISTS (
                    SELECT 1
                    FROM ecloe_pay.demo_users
                    WHERE email_normalized = :email_normalized
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
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    WHERE email_normalized = :email_normalized
                END
                """
            ),
            {"user_id": user_id, "email_normalized": email_normalized, "password_hash": password_hash},
        )
        row = connection.execute(
            text("SELECT COUNT(*) FROM ecloe_pay.demo_users WHERE email_normalized = :email_normalized"),
            {"email_normalized": email_normalized},
        ).scalar_one()

    print(f"ECloe Pay Azure SQL migration complete. Demo personas ready: {row}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
