from __future__ import annotations

import argparse
import re
import struct
import uuid

SQL_TOKEN_SCOPE = "https://database.windows.net/.default"
SQL_COPT_SS_ACCESS_TOKEN = 1256
DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"
DEFAULT_PRINCIPAL_NAME = "ecloe-demo-web"
DEFAULT_ROLE_NAME = "ecloe_demo_runtime"
RUNTIME_SCHEMAS = ("ecloe_pay", "ecloe_market")
RUNTIME_PERMISSIONS = ("SELECT", "INSERT", "UPDATE", "DELETE", "EXECUTE")


def _validated_identifier(value: str, field_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,127}", value):
        raise ValueError(f"{field_name} contains unsupported characters: {value!r}")
    return value


def _token_struct(token: str) -> bytes:
    encoded = token.encode("utf-16-le")
    return struct.pack(f"<I{len(encoded)}s", len(encoded), encoded)


def _connection_string(server: str, database: str, driver: str) -> str:
    return (
        f"Driver={{{driver}}};Server=tcp:{server},1433;Database={database};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )


def grant_runtime_access(
    *,
    server: str,
    database: str,
    principal_id: str,
    principal_name: str = DEFAULT_PRINCIPAL_NAME,
    role_name: str = DEFAULT_ROLE_NAME,
    driver: str = DEFAULT_DRIVER,
) -> None:
    principal_object_id = str(uuid.UUID(principal_id))
    principal_alias = _validated_identifier(principal_name, "principal_name")
    database_role = _validated_identifier(role_name, "role_name")

    try:
        import pyodbc
        from azure.identity import AzureCliCredential
    except ImportError as error:
        raise RuntimeError("Install the azure-sql project dependencies before running this script.") from error

    token = AzureCliCredential().get_token(SQL_TOKEN_SCOPE).token
    connection = pyodbc.connect(
        _connection_string(server, database, driver),
        attrs_before={SQL_COPT_SS_ACCESS_TOKEN: _token_struct(token)},
        autocommit=True,
    )
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM sys.database_principals WHERE name = ?", principal_alias)
        if cursor.fetchone() is None:
            cursor.execute(
                f"CREATE USER [{principal_alias}] FROM EXTERNAL PROVIDER "
                f"WITH OBJECT_ID = '{principal_object_id}'"
            )

        cursor.execute("SELECT 1 FROM sys.database_principals WHERE name = ? AND type = 'R'", database_role)
        if cursor.fetchone() is None:
            cursor.execute(f"CREATE ROLE [{database_role}]")

        for schema in RUNTIME_SCHEMAS:
            for permission in RUNTIME_PERMISSIONS:
                cursor.execute(f"GRANT {permission} ON SCHEMA::[{schema}] TO [{database_role}]")

        cursor.execute(
            "SELECT 1 FROM sys.database_role_members drm "
            "JOIN sys.database_principals role_principal ON role_principal.principal_id = drm.role_principal_id "
            "JOIN sys.database_principals member_principal ON member_principal.principal_id = drm.member_principal_id "
            "WHERE role_principal.name = ? AND member_principal.name = ?",
            database_role,
            principal_alias,
        )
        if cursor.fetchone() is None:
            cursor.execute(f"ALTER ROLE [{database_role}] ADD MEMBER [{principal_alias}]")
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Grant least-privilege ECloe demo Azure SQL access.")
    parser.add_argument("--server", default="ecloe-sql-1266.database.windows.net")
    parser.add_argument("--database", default="ecloe_validation")
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--principal-name", default=DEFAULT_PRINCIPAL_NAME)
    parser.add_argument("--role-name", default=DEFAULT_ROLE_NAME)
    parser.add_argument("--driver", default=DEFAULT_DRIVER)
    args = parser.parse_args()

    grant_runtime_access(
        server=args.server,
        database=args.database,
        principal_id=args.principal_id,
        principal_name=args.principal_name,
        role_name=args.role_name,
        driver=args.driver,
    )
    print(
        f"Granted {args.principal_name} access to ecloe_pay and ecloe_market "
        f"in {args.database}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
