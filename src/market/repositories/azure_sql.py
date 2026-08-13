from __future__ import annotations

import hashlib
import json
import struct
import uuid
from typing import Any

from src.core.config import Settings
from src.market.domain import (
    Cart,
    CartItem,
    Category,
    CheckoutSession,
    InventoryItem,
    Order,
    OrderItem,
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
        engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        if "attrs_before" in connect_args:
            from sqlalchemy import event

            @event.listens_for(engine, "do_connect")
            def _remove_sqlalchemy_trusted_connection(dialect, connection_record, cargs, cparams):
                if cargs:
                    cargs[0] = cargs[0].replace(";Trusted_Connection=Yes", "")

        return engine

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
        with self.engine.connect() as connection:
            return _load_cart(connection, session_key)

    def add_cart_item(
        self,
        *,
        session_key: str,
        product_id: str,
        variant_id: str | None = None,
        quantity: int = 1,
    ) -> Cart:
        from sqlalchemy import text

        detail = self.get_product_detail(product_id)
        if detail is None:
            raise ValueError("Synthetic ECloe Market product was not found.")
        selected_variant = detail.default_variant
        if variant_id:
            selected_variant = next(
                (variant for variant in detail.variants if variant.variant_id == variant_id),
                None,
            )
        if selected_variant is None:
            raise ValueError("Synthetic ECloe Market variant was not found.")
        price = next(
            (
                item
                for item in detail.current_prices
                if item.variant_id == selected_variant.variant_id and item.is_current
            ),
            None,
        )
        inventory = next(
            (item for item in detail.inventory_items if item.variant_id == selected_variant.variant_id),
            None,
        )
        if price is None or inventory is None:
            raise ValueError("Synthetic ECloe Market price or inventory was not found.")
        safe_quantity = max(min(quantity, 9), 1)
        cart_id = _cart_id(session_key)
        cart_item_id = _cart_item_id(cart_id, selected_variant.variant_id)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM ecloe_market.carts WITH (UPDLOCK, HOLDLOCK)
                        WHERE cart_id = :cart_id
                    )
                    BEGIN
                        INSERT INTO ecloe_market.carts (
                            cart_id, session_key_hash, status, currency, is_demo
                        ) VALUES (
                            :cart_id, :session_key_hash, N'active', 'BRL', 1
                        )
                    END
                    """
                ),
                {
                    "cart_id": cart_id,
                    "session_key_hash": _session_hash(session_key),
                },
            )
            existing = connection.execute(
                text(
                    """
                    SELECT quantity
                    FROM ecloe_market.cart_items WITH (UPDLOCK, HOLDLOCK)
                    WHERE cart_item_id = :cart_item_id
                    """
                ),
                {"cart_item_id": cart_item_id},
            ).scalar_one_or_none()
            new_quantity = min((int(existing) if existing is not None else 0) + safe_quantity, 9)
            if new_quantity > inventory.available_quantity:
                raise ValueError("Requested quantity exceeds synthetic inventory.")
            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM ecloe_market.cart_items WHERE cart_item_id = :cart_item_id
                    )
                    BEGIN
                        INSERT INTO ecloe_market.cart_items (
                            cart_item_id, cart_id, product_id, variant_id, quantity,
                            unit_price_cents, currency, is_demo
                        ) VALUES (
                            :cart_item_id, :cart_id, :product_id, :variant_id, :quantity,
                            :unit_price_cents, :currency, 1
                        )
                    END
                    ELSE
                    BEGIN
                        UPDATE ecloe_market.cart_items
                        SET quantity = :quantity,
                            unit_price_cents = :unit_price_cents,
                            updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                        WHERE cart_item_id = :cart_item_id
                    END
                    """
                ),
                {
                    "cart_item_id": cart_item_id,
                    "cart_id": cart_id,
                    "product_id": product_id,
                    "variant_id": selected_variant.variant_id,
                    "quantity": new_quantity,
                    "unit_price_cents": price.price_cents,
                    "currency": price.currency,
                },
            )
        return self.get_cart(session_key)

    def update_cart_item(self, *, session_key: str, cart_item_id: str, quantity: int) -> Cart:
        from sqlalchemy import text

        if quantity <= 0:
            return self.remove_cart_item(session_key=session_key, cart_item_id=cart_item_id)
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE ci
                    SET quantity = :quantity,
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    FROM ecloe_market.cart_items ci
                    JOIN ecloe_market.carts c ON c.cart_id = ci.cart_id
                    JOIN ecloe_market.inventory_items inventory
                        ON inventory.variant_id = ci.variant_id
                    WHERE ci.cart_item_id = :cart_item_id
                        AND c.session_key_hash = :session_key_hash
                        AND c.status = N'active'
                        AND :quantity <= inventory.available_quantity
                    """
                ),
                {
                    "quantity": min(quantity, 9),
                    "cart_item_id": cart_item_id,
                    "session_key_hash": _session_hash(session_key),
                },
            )
            if result.rowcount != 1:
                raise ValueError("Synthetic ECloe Market cart item was not found.")
        return self.get_cart(session_key)

    def remove_cart_item(self, *, session_key: str, cart_item_id: str) -> Cart:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE ci
                    FROM ecloe_market.cart_items ci
                    JOIN ecloe_market.carts c ON c.cart_id = ci.cart_id
                    WHERE ci.cart_item_id = :cart_item_id
                        AND c.session_key_hash = :session_key_hash
                        AND c.status = N'active'
                    """
                ),
                {
                    "cart_item_id": cart_item_id,
                    "session_key_hash": _session_hash(session_key),
                },
            )
        return self.get_cart(session_key)

    def start_checkout(
        self,
        *,
        session_key: str,
        user_id: str,
        idempotency_key: str,
    ) -> CheckoutSession:
        from sqlalchemy import text

        checkout_id = _checkout_id(idempotency_key)
        correlation_id = f"corr_{checkout_id}"
        with self.engine.begin() as connection:
            existing = connection.execute(
                text(
                    """
                    SELECT checkout_id, cart_id, user_id, status, total_cents, currency,
                        idempotency_key, correlation_id, CAST(is_demo AS bit) AS is_demo
                    FROM ecloe_market.checkout_sessions
                    WHERE idempotency_key = :idempotency_key
                    """
                ),
                {"idempotency_key": idempotency_key},
            ).mappings().first()
            if existing is not None:
                if existing["user_id"] != user_id:
                    raise ValueError("Checkout idempotency key belongs to another user.")
                return _checkout_from_row(existing)

            rows = list(
                connection.execute(
                    text(
                        """
                        SELECT c.cart_id, c.currency, ci.cart_item_id, ci.product_id,
                            ci.variant_id, ci.quantity, ci.unit_price_cents,
                            current_price.price_cents AS current_price_cents,
                            inventory.available_quantity
                        FROM ecloe_market.carts c WITH (UPDLOCK, HOLDLOCK)
                        JOIN ecloe_market.cart_items ci ON ci.cart_id = c.cart_id
                        CROSS APPLY (
                            SELECT TOP 1 pp.price_cents
                            FROM ecloe_market.product_prices pp
                            WHERE pp.variant_id = ci.variant_id AND pp.is_current = 1
                            ORDER BY pp.updated_at DESC, pp.price_id
                        ) current_price
                        JOIN ecloe_market.inventory_items inventory WITH (UPDLOCK, HOLDLOCK)
                            ON inventory.variant_id = ci.variant_id
                        WHERE c.session_key_hash = :session_key_hash AND c.status = N'active'
                        ORDER BY ci.cart_item_id
                        """
                    ),
                    {"session_key_hash": _session_hash(session_key)},
                ).mappings()
            )
            if not rows:
                raise ValueError("Synthetic ECloe Market cart must be active and non-empty.")
            for row in rows:
                if row["unit_price_cents"] != row["current_price_cents"]:
                    raise ValueError("Synthetic ECloe Market price changed before checkout.")
                if row["quantity"] > row["available_quantity"]:
                    raise ValueError("Requested quantity exceeds synthetic inventory.")
            total_cents = sum(row["quantity"] * row["current_price_cents"] for row in rows)
            snapshot = {
                "cart_id": rows[0]["cart_id"],
                "items": [
                    {
                        "cart_item_id": row["cart_item_id"],
                        "product_id": row["product_id"],
                        "variant_id": row["variant_id"],
                        "quantity": row["quantity"],
                        "unit_price_cents": row["current_price_cents"],
                    }
                    for row in rows
                ],
            }
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_market.checkout_sessions (
                        checkout_id, cart_id, user_id, status, total_cents, currency,
                        idempotency_key, correlation_id, context_snapshot_json, is_demo
                    ) VALUES (
                        :checkout_id, :cart_id, :user_id, N'created', :total_cents, 'BRL',
                        :idempotency_key, :correlation_id, :context_snapshot_json, 1
                    );
                    UPDATE ecloe_market.carts
                    SET status = N'checkout_started', user_id = :user_id,
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    WHERE cart_id = :cart_id;
                    INSERT INTO ecloe_market.outbox_events (
                        outbox_event_id, aggregate_id, event_type, payload_json, status, is_demo
                    ) VALUES (
                        :outbox_event_id, :checkout_id, N'market.checkout_started',
                        :outbox_payload, N'pending', 1
                    );
                    """
                ),
                {
                    "checkout_id": checkout_id,
                    "cart_id": rows[0]["cart_id"],
                    "user_id": user_id,
                    "total_cents": total_cents,
                    "idempotency_key": idempotency_key,
                    "correlation_id": correlation_id,
                    "context_snapshot_json": json.dumps(snapshot, sort_keys=True),
                    "outbox_event_id": f"out_market_{uuid.uuid4().hex}",
                    "outbox_payload": json.dumps(
                        {
                            "checkout_id": checkout_id,
                            "cart_id": rows[0]["cart_id"],
                            "total_cents": total_cents,
                            "currency": "BRL",
                        },
                        sort_keys=True,
                    ),
                },
            )
        checkout = self.get_checkout(checkout_id=checkout_id, user_id=user_id)
        if checkout is None:
            raise RuntimeError("Checkout transaction committed without a readable checkout.")
        return checkout

    def get_checkout(self, *, checkout_id: str, user_id: str) -> CheckoutSession | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT checkout_id, cart_id, user_id, status, total_cents, currency,
                        idempotency_key, correlation_id, CAST(is_demo AS bit) AS is_demo
                    FROM ecloe_market.checkout_sessions
                    WHERE checkout_id = :checkout_id AND user_id = :user_id
                    """
                ),
                {"checkout_id": checkout_id, "user_id": user_id},
            ).mappings().first()
        return _checkout_from_row(row) if row is not None else None

    def create_order(self, *, checkout_id: str, user_id: str) -> Order:
        from sqlalchemy import text

        order_id = _order_id(checkout_id)
        with self.engine.begin() as connection:
            existing = _load_order(connection, order_id, user_id)
            if existing is not None:
                return existing
            checkout = connection.execute(
                text(
                    """
                    SELECT checkout_id, cart_id, user_id, status, total_cents, currency,
                        correlation_id
                    FROM ecloe_market.checkout_sessions WITH (UPDLOCK, HOLDLOCK)
                    WHERE checkout_id = :checkout_id AND user_id = :user_id
                    """
                ),
                {"checkout_id": checkout_id, "user_id": user_id},
            ).mappings().first()
            if checkout is None or checkout["status"] not in {"created", "payment_pending"}:
                raise ValueError("Synthetic ECloe Market checkout is not ready for order creation.")
            rows = list(
                connection.execute(
                    text(
                        """
                        SELECT ci.cart_item_id, ci.product_id, ci.variant_id, p.title_en,
                            ci.quantity, ci.unit_price_cents, ci.currency,
                            current_price.price_cents AS current_price_cents,
                            inventory.available_quantity
                        FROM ecloe_market.cart_items ci
                        JOIN ecloe_market.products p ON p.product_id = ci.product_id
                        CROSS APPLY (
                            SELECT TOP 1 pp.price_cents
                            FROM ecloe_market.product_prices pp
                            WHERE pp.variant_id = ci.variant_id AND pp.is_current = 1
                            ORDER BY pp.updated_at DESC, pp.price_id
                        ) current_price
                        JOIN ecloe_market.inventory_items inventory WITH (UPDLOCK, HOLDLOCK)
                            ON inventory.variant_id = ci.variant_id
                        WHERE ci.cart_id = :cart_id
                        ORDER BY ci.cart_item_id
                        """
                    ),
                    {"cart_id": checkout["cart_id"]},
                ).mappings()
            )
            if not rows:
                raise ValueError("Synthetic ECloe Market checkout cart is empty.")
            for row in rows:
                if row["unit_price_cents"] != row["current_price_cents"]:
                    raise ValueError("Synthetic ECloe Market price changed before order creation.")
                if row["quantity"] > row["available_quantity"]:
                    raise ValueError("Requested quantity exceeds synthetic inventory.")
            current_total = sum(row["quantity"] * row["current_price_cents"] for row in rows)
            if current_total != checkout["total_cents"]:
                raise ValueError("Synthetic ECloe Market checkout total changed before order creation.")
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_market.orders (
                        order_id, checkout_id, user_id, status, total_cents,
                        currency, correlation_id, is_demo
                    ) VALUES (
                        :order_id, :checkout_id, :user_id, N'payment_pending',
                        :total_cents, :currency, :correlation_id, 1
                    );
                    UPDATE ecloe_market.checkout_sessions
                    SET status = N'payment_pending',
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    WHERE checkout_id = :checkout_id;
                    """
                ),
                {
                    "order_id": order_id,
                    "checkout_id": checkout_id,
                    "user_id": user_id,
                    "total_cents": current_total,
                    "currency": checkout["currency"],
                    "correlation_id": checkout["correlation_id"],
                },
            )
            for row in rows:
                connection.execute(
                    text(
                        """
                        INSERT INTO ecloe_market.order_items (
                            order_item_id, order_id, product_id, variant_id, title_snapshot,
                            quantity, unit_price_cents, currency, is_demo
                        ) VALUES (
                            :order_item_id, :order_id, :product_id, :variant_id, :title_snapshot,
                            :quantity, :unit_price_cents, :currency, 1
                        )
                        """
                    ),
                    {
                        "order_item_id": _order_item_id(order_id, row["variant_id"]),
                        "order_id": order_id,
                        "product_id": row["product_id"],
                        "variant_id": row["variant_id"],
                        "title_snapshot": row["title_en"],
                        "quantity": row["quantity"],
                        "unit_price_cents": row["current_price_cents"],
                        "currency": row["currency"],
                    },
                )
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_market.outbox_events (
                        outbox_event_id, aggregate_id, event_type, payload_json, status, is_demo
                    ) VALUES (
                        :outbox_event_id, :order_id, N'market.order_created',
                        :payload_json, N'pending', 1
                    )
                    """
                ),
                {
                    "outbox_event_id": f"out_market_{uuid.uuid4().hex}",
                    "order_id": order_id,
                    "payload_json": json.dumps(
                        {
                            "order_id": order_id,
                            "checkout_id": checkout_id,
                            "status": "payment_pending",
                            "total_cents": current_total,
                            "currency": checkout["currency"],
                        },
                        sort_keys=True,
                    ),
                },
            )
            order = _load_order(connection, order_id, user_id)
        if order is None:
            raise RuntimeError("Order transaction committed without a readable order.")
        return order

    def list_orders(self, *, user_id: str) -> list[Order]:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            order_ids = connection.execute(
                text(
                    """
                    SELECT order_id FROM ecloe_market.orders
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC, order_id
                    """
                ),
                {"user_id": user_id},
            ).scalars()
            return [
                order
                for order_id in order_ids
                if (order := _load_order(connection, order_id, user_id)) is not None
            ]

    def record_recommendation_interaction(
        self,
        *,
        event_id: str,
        session_key: str,
        decision_id: str,
        product_id: str,
        position: int,
        event_type: str,
    ) -> None:
        from sqlalchemy import text

        payload = {
            "event_id": event_id,
            "decision_id": decision_id,
            "product_id": product_id,
            "position": position,
            "event_type": event_type,
        }
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM ecloe_market.recommendation_interactions
                        WHERE event_id = :event_id
                    )
                    BEGIN
                        INSERT INTO ecloe_market.recommendation_interactions (
                            interaction_id, event_id, session_key_hash, decision_id,
                            product_id, position, event_type
                        ) VALUES (
                            :interaction_id, :event_id, :session_key_hash, :decision_id,
                            :product_id, :position, :event_type
                        );
                        INSERT INTO ecloe_market.outbox_events (
                            outbox_event_id, aggregate_id, event_type, payload_json,
                            status, is_demo
                        ) VALUES (
                            :outbox_event_id, :decision_id, :event_type, :payload_json,
                            N'pending', 1
                        );
                    END
                    """
                ),
                {
                    "interaction_id": f"int_market_{uuid.uuid4().hex}",
                    "outbox_event_id": f"out_market_{uuid.uuid4().hex}",
                    "event_id": event_id,
                    "session_key_hash": _session_hash(session_key),
                    "decision_id": decision_id,
                    "product_id": product_id,
                    "position": position,
                    "event_type": event_type,
                    "payload_json": json.dumps(payload, sort_keys=True),
                },
            )


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


def _load_cart(connection: Any, session_key: str) -> Cart:
    from sqlalchemy import text

    row = connection.execute(
        text(
            """
            SELECT TOP 1 cart_id, status, currency, CAST(is_demo AS bit) AS is_demo
            FROM ecloe_market.carts
            WHERE session_key_hash = :session_key_hash AND status = N'active'
            ORDER BY created_at DESC
            """
        ),
        {"session_key_hash": _session_hash(session_key)},
    ).mappings().first()
    if row is None:
        return Cart(cart_id=_cart_id(session_key), session_key=session_key, status="active", items=())
    items = connection.execute(
        text(
            """
            SELECT ci.cart_item_id, ci.cart_id, ci.product_id, ci.variant_id,
                p.title_en AS title, ci.quantity, ci.unit_price_cents, ci.currency,
                p.thumbnail, CAST(ci.is_demo AS bit) AS is_demo
            FROM ecloe_market.cart_items ci
            JOIN ecloe_market.products p ON p.product_id = ci.product_id
            WHERE ci.cart_id = :cart_id
            ORDER BY ci.created_at, ci.cart_item_id
            """
        ),
        {"cart_id": row["cart_id"]},
    ).mappings()
    return Cart(
        cart_id=row["cart_id"],
        session_key=session_key,
        status=row["status"],
        items=tuple(CartItem(**dict(item)) for item in items),
        currency=row["currency"],
        is_demo=bool(row["is_demo"]),
    )


def _session_hash(session_key: str) -> str:
    return hashlib.sha256(session_key.encode()).hexdigest()


def _cart_id(session_key: str) -> str:
    return f"cart_demo_{_session_hash(session_key)[:16]}"


def _cart_item_id(cart_id: str, variant_id: str) -> str:
    digest = hashlib.sha256(f"{cart_id}:{variant_id}".encode()).hexdigest()[:16]
    return f"cart_item_{digest}"


def _checkout_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:20]
    return f"checkout_demo_{digest}"


def _order_id(checkout_id: str) -> str:
    digest = hashlib.sha256(checkout_id.encode()).hexdigest()[:20]
    return f"order_demo_{digest}"


def _order_item_id(order_id: str, variant_id: str) -> str:
    digest = hashlib.sha256(f"{order_id}:{variant_id}".encode()).hexdigest()[:20]
    return f"order_item_{digest}"


def _checkout_from_row(row: Any) -> CheckoutSession:
    return CheckoutSession(
        checkout_id=row["checkout_id"],
        cart_id=row["cart_id"],
        user_id=row["user_id"],
        status=row["status"],
        total_cents=row["total_cents"],
        currency=row["currency"],
        idempotency_key=row["idempotency_key"],
        correlation_id=row["correlation_id"],
        is_demo=bool(row["is_demo"]),
    )


def _load_order(connection: Any, order_id: str, user_id: str) -> Order | None:
    from sqlalchemy import text

    row = connection.execute(
        text(
            """
            SELECT order_id, checkout_id, user_id, status, total_cents, currency,
                CAST(is_demo AS bit) AS is_demo
            FROM ecloe_market.orders
            WHERE order_id = :order_id AND user_id = :user_id
            """
        ),
        {"order_id": order_id, "user_id": user_id},
    ).mappings().first()
    if row is None:
        return None
    items = connection.execute(
        text(
            """
            SELECT order_item_id, order_id, product_id, variant_id, title_snapshot,
                quantity, unit_price_cents, currency, CAST(is_demo AS bit) AS is_demo
            FROM ecloe_market.order_items
            WHERE order_id = :order_id
            ORDER BY order_item_id
            """
        ),
        {"order_id": order_id},
    ).mappings()
    return Order(
        order_id=row["order_id"],
        checkout_id=row["checkout_id"],
        user_id=row["user_id"],
        status=row["status"],
        items=tuple(OrderItem(**dict(item)) for item in items),
        total_cents=row["total_cents"],
        currency=row["currency"],
        is_demo=bool(row["is_demo"]),
    )
