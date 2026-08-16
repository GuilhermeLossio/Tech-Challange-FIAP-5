from __future__ import annotations


def strip_sqlalchemy_trusted_connection(connection_string: str) -> str:
    """Remove SQLAlchemy's implicit Windows authentication from token-based ODBC connections."""
    return connection_string.replace(";Trusted_Connection=Yes", "")
