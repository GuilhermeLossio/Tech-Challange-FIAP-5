from __future__ import annotations

from typing import Protocol

from src.market.domain import Cart, Category, Product, ProductDetail


class MarketRepository(Protocol):
    def list_categories(self) -> list[Category]:
        ...

    def list_products(
        self,
        *,
        category_id: str | None = None,
        query: str | None = None,
        sort: str = "featured",
        limit: int = 24,
        offset: int = 0,
    ) -> list[Product]:
        ...

    def get_product(self, product_id: str) -> Product | None:
        ...

    def get_product_detail(self, product_id: str) -> ProductDetail | None:
        ...

    def get_cart(self, session_key: str) -> Cart:
        ...

    def add_cart_item(
        self,
        *,
        session_key: str,
        product_id: str,
        variant_id: str | None = None,
        quantity: int = 1,
    ) -> Cart:
        ...

    def update_cart_item(self, *, session_key: str, cart_item_id: str, quantity: int) -> Cart:
        ...

    def remove_cart_item(self, *, session_key: str, cart_item_id: str) -> Cart:
        ...
