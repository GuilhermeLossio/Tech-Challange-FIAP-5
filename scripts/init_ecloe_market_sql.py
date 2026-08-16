from __future__ import annotations

import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.config import load_settings
from src.market.application.catalog_loader import Catalog, load_catalog

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "src" / "market" / "infrastructure" / "schema.sql"
MIGRATION_ID = "20260803_ecloe_market_catalog_pr2"
SQL_TOKEN_SCOPE = "https://database.windows.net/.default"
SUPPORTED_ODBC_DRIVERS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server")


@dataclass(frozen=True)
class InitMarketSummary:
    schema_ok: bool
    migrations_applied: int
    categories_seeded: int
    products_seeded: int
    variants_seeded: int
    prices_seeded: int
    inventory_items_seeded: int


def _available_odbc_drivers() -> set[str]:
    try:
        import pyodbc
    except ModuleNotFoundError as error:
        raise RuntimeError("pyodbc is required. Install the azure-sql extra first.") from error
    return set(pyodbc.drivers())


def _resolve_odbc_driver(driver_name: str) -> str:
    available = _available_odbc_drivers()
    if driver_name in available and driver_name in SUPPORTED_ODBC_DRIVERS:
        return driver_name

    for fallback in SUPPORTED_ODBC_DRIVERS:
        if fallback in available:
            if driver_name != fallback:
                print(
                    "ECloe Market Azure SQL: "
                    f"configured driver '{driver_name}' was not found; using installed '{fallback}'."
                )
            return fallback

    installed = ", ".join(sorted(available)) if available else "none"
    raise RuntimeError(
        "Microsoft ODBC Driver 18 for SQL Server is required for ECloe Market Azure SQL "
        f"(ODBC Driver 17 is accepted as a local fallback). Configured: '{driver_name}'. "
        f"Installed ODBC drivers: {installed}. Install Microsoft ODBC Driver 18 for SQL Server "
        "or set ECLOE_PAY_SQL_DRIVER to a supported installed driver."
    )


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


def _engine_with_entra_token(settings: Any, access_token: str, driver_name: str) -> Any:
    try:
        from sqlalchemy import URL, create_engine, event
    except ModuleNotFoundError as error:
        raise RuntimeError("SQLAlchemy is required. Install the azure-sql extra first.") from error

    token_bytes = access_token.encode("utf-16-le")
    attrs_before = {1256: struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)}
    url = URL.create(
        "mssql+pyodbc",
        host=settings.ecloe_pay_sql_server,
        database=settings.ecloe_pay_sql_database,
        query={
            "driver": driver_name,
            "Encrypt": "yes",
            "TrustServerCertificate": "no",
            "Connection Timeout": "30",
        },
    )
    engine = create_engine(url, connect_args={"attrs_before": attrs_before}, pool_pre_ping=True)

    @event.listens_for(engine, "do_connect")
    def _remove_sqlalchemy_trusted_connection(dialect, connection_record, cargs, cparams):
        if cargs:
            cargs[0] = cargs[0].replace(";Trusted_Connection=Yes", "")

    return engine


def _sql_statement(statement: str) -> Any:
    try:
        from sqlalchemy import text
    except ModuleNotFoundError:
        return statement
    return text(statement)


def _schema_migration_applied(connection: Any) -> bool:
    exists = connection.execute(
        _sql_statement(
            "SELECT CASE WHEN OBJECT_ID(N'ecloe_market.schema_migrations', N'U') IS NULL THEN 0 ELSE 1 END"
        )
    ).scalar_one()
    if not exists:
        return False
    return bool(
        connection.execute(
            _sql_statement(
                """
                SELECT COUNT(*)
                FROM ecloe_market.schema_migrations
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


def _seed_catalog(connection: Any, catalog: Catalog) -> InitMarketSummary:
    for sort_order, category in enumerate(catalog.categories, start=1):
        connection.execute(
            _sql_statement(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM ecloe_market.categories WHERE category_id = :category_id
                )
                BEGIN
                    INSERT INTO ecloe_market.categories (
                        category_id, slug, title_pt, title_en, sort_order, is_demo
                    )
                    VALUES (
                        :category_id, :slug, :title_pt, :title_en, :sort_order, :is_demo
                    )
                END
                ELSE
                BEGIN
                    UPDATE ecloe_market.categories
                    SET slug = :slug,
                        title_pt = :title_pt,
                        title_en = :title_en,
                        sort_order = :sort_order,
                        is_demo = :is_demo,
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    WHERE category_id = :category_id
                END
                """
            ),
            {**category.__dict__, "sort_order": sort_order},
        )

    for product in catalog.products:
        connection.execute(
            _sql_statement(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM ecloe_market.products WHERE product_id = :product_id
                )
                BEGIN
                    INSERT INTO ecloe_market.products (
                        product_id, source, source_id, slug, title_pt, title_en,
                        description_pt, description_en, category_id, brand, sku,
                        price_cents, currency, stock_quantity, rating, thumbnail,
                        images_json, is_demo, status
                    )
                    VALUES (
                        :product_id, :source, :source_id, :slug, :title_pt, :title_en,
                        :description_pt, :description_en, :category_id, :brand, :sku,
                        :price_cents, :currency, :stock_quantity, :rating, :thumbnail,
                        :images_json, :is_demo, :status
                    )
                END
                ELSE
                BEGIN
                    UPDATE ecloe_market.products
                    SET source = :source,
                        source_id = :source_id,
                        slug = :slug,
                        title_pt = :title_pt,
                        title_en = :title_en,
                        description_pt = :description_pt,
                        description_en = :description_en,
                        category_id = :category_id,
                        brand = :brand,
                        sku = :sku,
                        price_cents = :price_cents,
                        currency = :currency,
                        stock_quantity = :stock_quantity,
                        rating = :rating,
                        thumbnail = :thumbnail,
                        images_json = :images_json,
                        is_demo = :is_demo,
                        status = :status,
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    WHERE product_id = :product_id
                END
                """
            ),
            {**product.__dict__, "images_json": json.dumps(product.images)},
        )

    for variant in catalog.variants:
        connection.execute(
            _sql_statement(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM ecloe_market.product_variants WHERE variant_id = :variant_id
                )
                BEGIN
                    INSERT INTO ecloe_market.product_variants (
                        variant_id, product_id, sku, title_pt, title_en, is_default, is_demo, status
                    )
                    VALUES (
                        :variant_id, :product_id, :sku, :title_pt, :title_en,
                        :is_default, :is_demo, :status
                    )
                END
                ELSE
                BEGIN
                    UPDATE ecloe_market.product_variants
                    SET product_id = :product_id,
                        sku = :sku,
                        title_pt = :title_pt,
                        title_en = :title_en,
                        is_default = :is_default,
                        is_demo = :is_demo,
                        status = :status,
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    WHERE variant_id = :variant_id
                END
                """
            ),
            variant.__dict__,
        )

    for price in catalog.prices:
        connection.execute(
            _sql_statement(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM ecloe_market.product_prices WHERE price_id = :price_id
                )
                BEGIN
                    INSERT INTO ecloe_market.product_prices (
                        price_id, variant_id, price_cents, currency, is_current, is_demo
                    )
                    VALUES (
                        :price_id, :variant_id, :price_cents, :currency, :is_current, :is_demo
                    )
                END
                ELSE
                BEGIN
                    UPDATE ecloe_market.product_prices
                    SET variant_id = :variant_id,
                        price_cents = :price_cents,
                        currency = :currency,
                        is_current = :is_current,
                        is_demo = :is_demo,
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    WHERE price_id = :price_id
                END
                """
            ),
            price.__dict__,
        )

    for inventory in catalog.inventory_items:
        connection.execute(
            _sql_statement(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM ecloe_market.inventory_items WHERE inventory_id = :inventory_id
                )
                BEGIN
                    INSERT INTO ecloe_market.inventory_items (
                        inventory_id, variant_id, available_quantity, reserved_quantity, is_demo
                    )
                    VALUES (
                        :inventory_id, :variant_id, :available_quantity, :reserved_quantity, :is_demo
                    )
                END
                ELSE
                BEGIN
                    UPDATE ecloe_market.inventory_items
                    SET variant_id = :variant_id,
                        available_quantity = :available_quantity,
                        reserved_quantity = :reserved_quantity,
                        is_demo = :is_demo,
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    WHERE inventory_id = :inventory_id
                END
                """
            ),
            inventory.__dict__,
        )

    return InitMarketSummary(
        schema_ok=True,
        migrations_applied=0,
        categories_seeded=len(catalog.categories),
        products_seeded=len(catalog.products),
        variants_seeded=len(catalog.variants),
        prices_seeded=len(catalog.prices),
        inventory_items_seeded=len(catalog.inventory_items),
    )


def initialize_market_sql(settings: Any | None = None) -> InitMarketSummary:
    settings = settings or load_settings()
    driver_name = _resolve_odbc_driver(settings.ecloe_pay_sql_driver)
    catalog = load_catalog(settings.ecloe_market_catalog_path)
    access_token = _entra_access_token(settings.ecloe_pay_sql_auth_mode)
    engine = _engine_with_entra_token(settings, access_token, driver_name)

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            migrations_applied = _apply_schema(connection)
            summary = _seed_catalog(connection, catalog)
        except Exception:
            transaction.rollback()
            raise
        else:
            transaction.commit()
    return InitMarketSummary(
        schema_ok=summary.schema_ok,
        migrations_applied=migrations_applied,
        categories_seeded=summary.categories_seeded,
        products_seeded=summary.products_seeded,
        variants_seeded=summary.variants_seeded,
        prices_seeded=summary.prices_seeded,
        inventory_items_seeded=summary.inventory_items_seeded,
    )


def main() -> int:
    try:
        summary = initialize_market_sql()
    except RuntimeError as error:
        print(f"ECloe Market Azure SQL initialization failed: {error}", file=sys.stderr)
        return 1
    print(
        "ECloe Market Azure SQL initialized: "
        f"schema_ok={summary.schema_ok}; "
        f"migrations_applied={summary.migrations_applied}; "
        f"categories={summary.categories_seeded}; "
        f"products={summary.products_seeded}; "
        f"variants={summary.variants_seeded}; "
        f"prices={summary.prices_seeded}; "
        f"inventory_items={summary.inventory_items_seeded}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
