from __future__ import annotations

import json
import struct
from typing import Any

from src.core.config import Settings
from src.market.domain import (
    Cart,
    Category,
    InventoryItem,
    Product,
    ProductDetail,
    ProductPrice,
    ProductVariant,
)
from src.market.repositories.memory import ALLOWED_SORTS
from src.market.repositories.protocols import MarketRepository


class AzureSqlMarketRepository(MarketRepository):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = self._create_engine()

    def _create_engine(self) -> Any:
        try:
            from sqlalchemy import URL, create_engine
        except ModuleNotFoundError as error:
            raise RuntimeError("Install the azure-sql extra to use ECLOE_MARKET_DATABASE_MODE=azure_sql.") from error

        query = {
            "driver": self.settings.ecloe_pay_sql_driver,
            "Encrypt": "yes",
            "TrustServerCertificate": "no",
            "Connection Timeout": "30",
        }
        connect_args: dict[str, object] = {}
        if self.settings.ecloe_pay_sql_auth_mode == "entra_interactive":
            query["Authentication"] = "ActiveDirectoryInteractive"
        elif self.settings.ecloe_pay_sql_auth_mode == "managed_identity":
            query["Authentication"] = "ActiveDirectoryMsi"
        elif self.settings.ecloe_pay_sql_auth_mode == "azure_cli":
            try:
                from azure.identity import AzureCliCredential
            except ModuleNotFoundError as error:
                raise RuntimeError("azure-identity is required for ECLOE_PAY_SQL_AUTH_MODE=azure_cli.") from error
            token = AzureCliCredential().get_token("https://database.windows.net/.default").token
            token_bytes = token.encode("utf-16-le")
            connect_args["attrs_before"] = {
                1256: struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
            }

        url = URL.create(
            "mssql+pyodbc",
            host=self.settings.ecloe_pay_sql_server,
            database=self.settings.ecloe_pay_sql_database,
            query=query,
        )
        return create_engine(url, connect_args=connect_args, pool_pre_ping=True)

    def list_categories(self) -> list[Category]:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT category_id, slug, title_pt, title_en, CAST(is_demo AS bit) AS is_demo
                    FROM ecloe_market.categories
                    WHERE is_demo = 1
                    ORDER BY sort_order, title_en
                    """
                )
            ).mappings()
            return [Category(**dict(row)) for row in rows]

    def list_products(
        self,
        *,
        category_id: str | None = None,
        query: str | None = None,
        sort: str = "featured",
        limit: int = 24,
        offset: int = 0,
    ) -> list[Product]:
        from sqlalchemy import text

        sort = sort if sort in ALLOWED_SORTS else "featured"
        order_clause = {
            "featured": "p.product_id ASC",
            "price_asc": "p.price_cents ASC, p.title_en ASC",
            "price_desc": "p.price_cents DESC, p.title_en ASC",
            "title": "p.title_en ASC",
        }[sort]
        statement = text(
            f"""
            SELECT
                p.product_id, p.source, p.source_id, p.slug, p.title_pt, p.title_en,
                p.description_pt, p.description_en, p.category_id, p.brand, p.sku,
                p.price_cents, p.currency, p.stock_quantity, p.rating, p.thumbnail,
                p.images_json, CAST(p.is_demo AS bit) AS is_demo, p.status
            FROM ecloe_market.products p
            WHERE p.is_demo = 1
                AND p.status = N'active'
                AND (:category_id IS NULL OR p.category_id = :category_id)
                AND (
                    :query IS NULL
                    OR p.title_pt LIKE :like_query
                    OR p.title_en LIKE :like_query
                    OR p.description_pt LIKE :like_query
                    OR p.description_en LIKE :like_query
                )
            ORDER BY {order_clause}
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
            """
        )
        params = _product_list_params(category_id, query, limit, offset)
        with self.engine.connect() as connection:
            rows = connection.execute(statement, params).mappings()
            return [_product_from_row(row) for row in rows]

    def get_product(self, product_id: str) -> Product | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        product_id, source, source_id, slug, title_pt, title_en,
                        description_pt, description_en, category_id, brand, sku,
                        price_cents, currency, stock_quantity, rating, thumbnail,
                        images_json, CAST(is_demo AS bit) AS is_demo, status
                    FROM ecloe_market.products
                    WHERE product_id = :product_id
                        AND is_demo = 1
                    """
                ),
                {"product_id": product_id},
            ).mappings().first()
        return _product_from_row(row) if row else None

    def get_product_detail(self, product_id: str) -> ProductDetail | None:
        from sqlalchemy import text

        product = self.get_product(product_id)
        if product is None:
            return None
        with self.engine.connect() as connection:
            variants = [
                ProductVariant(**dict(row))
                for row in connection.execute(
                    text(
                        """
                        SELECT
                            variant_id, product_id, sku, title_pt, title_en,
                            CAST(is_default AS bit) AS is_default,
                            CAST(is_demo AS bit) AS is_demo,
                            status
                        FROM ecloe_market.product_variants
                        WHERE product_id = :product_id
                            AND is_demo = 1
                            AND status = N'active'
                        ORDER BY is_default DESC, variant_id ASC
                        """
                    ),
                    {"product_id": product_id},
                ).mappings()
            ]
            variant_ids = [variant.variant_id for variant in variants]
            prices: list[ProductPrice] = []
            inventory_items: list[InventoryItem] = []
            if variant_ids:
                rows = connection.execute(
                    text(
                        """
                        SELECT
                            price_id, variant_id, price_cents, currency,
                            CAST(is_current AS bit) AS is_current,
                            CAST(is_demo AS bit) AS is_demo
                        FROM ecloe_market.product_prices
                        WHERE is_current = 1
                            AND is_demo = 1
                            AND variant_id IN :variant_ids
                        """
                    ).bindparams(_expanding_param("variant_ids")),
                    {"variant_ids": variant_ids},
                ).mappings()
                prices = [ProductPrice(**dict(row)) for row in rows]
                rows = connection.execute(
                    text(
                        """
                        SELECT
                            inventory_id, variant_id, available_quantity,
                            reserved_quantity, CAST(is_demo AS bit) AS is_demo
                        FROM ecloe_market.inventory_items
                        WHERE is_demo = 1
                            AND variant_id IN :variant_ids
                        """
                    ).bindparams(_expanding_param("variant_ids")),
                    {"variant_ids": variant_ids},
                ).mappings()
                inventory_items = [InventoryItem(**dict(row)) for row in rows]
        return ProductDetail(
            product=product,
            variants=tuple(variants),
            current_prices=tuple(prices),
            inventory_items=tuple(inventory_items),
        )

    def get_cart(self, session_key: str) -> Cart:
        raise NotImplementedError("ECloe Market Azure SQL cart persistence is planned for the next slice.")

    def add_cart_item(
        self,
        *,
        session_key: str,
        product_id: str,
        variant_id: str | None = None,
        quantity: int = 1,
    ) -> Cart:
        raise NotImplementedError("ECloe Market Azure SQL cart persistence is planned for the next slice.")

    def update_cart_item(self, *, session_key: str, cart_item_id: str, quantity: int) -> Cart:
        raise NotImplementedError("ECloe Market Azure SQL cart persistence is planned for the next slice.")

    def remove_cart_item(self, *, session_key: str, cart_item_id: str) -> Cart:
        raise NotImplementedError("ECloe Market Azure SQL cart persistence is planned for the next slice.")


def _expanding_param(name: str):
    from sqlalchemy import bindparam

    return bindparam(name, expanding=True)


def _product_list_params(
    category_id: str | None,
    query: str | None,
    limit: int,
    offset: int,
) -> dict[str, object]:
    normalized_query = query.strip() if query else None
    return {
        "category_id": category_id or None,
        "query": normalized_query,
        "like_query": f"%{normalized_query}%" if normalized_query else None,
        "limit": max(min(limit, 60), 1),
        "offset": max(offset, 0),
    }


def _product_from_row(row: Any) -> Product:
    values = dict(row)
    images_json = values.pop("images_json")
    return Product(
        **{
            **values,
            "images": tuple(json.loads(images_json or "[]")),
        }
    )
