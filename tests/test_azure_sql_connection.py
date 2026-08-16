from src.core.azure_sql import strip_sqlalchemy_trusted_connection


def test_strip_sqlalchemy_trusted_connection_preserves_managed_identity_authentication() -> None:
    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};Server=tcp:ecloe-sql.database.windows.net;"
        "Database=ecloe_validation;Trusted_Connection=Yes;Authentication=ActiveDirectoryMsi"
    )

    result = strip_sqlalchemy_trusted_connection(connection_string)

    assert "Trusted_Connection" not in result
    assert "Authentication=ActiveDirectoryMsi" in result
