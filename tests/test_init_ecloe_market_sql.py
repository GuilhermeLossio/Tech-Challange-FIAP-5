from scripts import init_ecloe_market_sql
from src.core.config import load_settings
from src.market.application.catalog_loader import load_catalog


def test_ecloe_market_init_schema_is_idempotent_and_market_scoped() -> None:
    schema = init_ecloe_market_sql.SCHEMA_FILE.read_text(encoding="utf-8")

    assert "IF NOT EXISTS" in schema
    assert "ecloe_market.schema_migrations" in schema
    assert init_ecloe_market_sql.MIGRATION_ID in schema
    assert "ecloe_pay" not in schema


def test_ecloe_market_seed_uses_parameterized_sql_and_safe_summary(capsys) -> None:
    settings = load_settings(use_env_file=False)
    catalog = load_catalog(settings.ecloe_market_catalog_path)
    connection = RecordingConnection()

    summary = init_ecloe_market_sql._seed_catalog(connection, catalog)
    print(
        "ECloe Market Azure SQL initialized: "
        f"categories={summary.categories_seeded}; products={summary.products_seeded}"
    )
    output = capsys.readouterr().out

    assert summary.categories_seeded == 6
    assert summary.products_seeded == 60
    assert summary.variants_seeded == 60
    assert summary.prices_seeded == 60
    assert summary.inventory_items_seeded == 60
    assert connection.executions
    assert all(isinstance(params, dict) for _, params in connection.executions)
    assert "Glow balm" not in output
    assert "ECLOE-0001" not in output


def test_ecloe_market_driver_resolution_accepts_installed_17_fallback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        init_ecloe_market_sql,
        "_available_odbc_drivers",
        lambda: {"ODBC Driver 17 for SQL Server"},
    )

    driver = init_ecloe_market_sql._resolve_odbc_driver("ODBC Driver 18 for SQL Server")

    assert driver == "ODBC Driver 17 for SQL Server"
    assert "using installed 'ODBC Driver 17 for SQL Server'" in capsys.readouterr().out


def test_ecloe_market_driver_resolution_rejects_legacy_sql_server_driver(monkeypatch) -> None:
    monkeypatch.setattr(
        init_ecloe_market_sql,
        "_available_odbc_drivers",
        lambda: {"SQL Server"},
    )

    try:
        init_ecloe_market_sql._resolve_odbc_driver("ODBC Driver 18 for SQL Server")
    except RuntimeError as error:
        message = str(error)
    else:
        raise AssertionError("Expected unsupported driver resolution to fail.")

    assert "Microsoft ODBC Driver 18 for SQL Server is required" in message
    assert "Installed ODBC drivers: SQL Server" in message
    assert "ECLOE_PAY_SQL_DRIVER" in message


class RecordingConnection:
    def __init__(self) -> None:
        self.executions = []

    def execute(self, statement, params=None):
        self.executions.append((str(statement), params or {}))
        return self
