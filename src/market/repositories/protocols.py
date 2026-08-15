from __future__ import annotations

from typing import Protocol

from src.market.domain import (
    Cart,
    Category,
    CheckoutItemRequest,
    CheckoutSession,
    Order,
    Product,
    ProductDetail,
)


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

    def clear_cart(self, *, session_key: str) -> Cart:
        ...

    def start_checkout(
        self,
        *,
        session_key: str,
        user_id: str,
        idempotency_key: str,
    ) -> CheckoutSession:
        ...

    def start_checkout_from_items(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        items: tuple[CheckoutItemRequest, ...],
    ) -> CheckoutSession:
        ...

    def get_checkout(self, *, checkout_id: str, user_id: str) -> CheckoutSession | None:
        ...

    def create_order(self, *, checkout_id: str, user_id: str) -> Order:
        ...

    def release_checkout_cart(self, *, checkout_id: str, user_id: str) -> None:
        ...

    def mark_order_paid(
        self,
        *,
        order_id: str,
        user_id: str,
        payment_id: str,
        pay_payment_order_id: str,
        amount_cents: int,
        currency: str,
    ) -> Order:
        ...

    def list_orders(self, *, user_id: str) -> list[Order]:
        ...

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
        ...
