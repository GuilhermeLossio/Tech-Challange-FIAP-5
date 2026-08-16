from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckoutItemRequest:
    product_id: str
    variant_id: str | None
    quantity: int
    expected_unit_price_cents: int


@dataclass(frozen=True)
class CartItem:
    cart_item_id: str
    cart_id: str
    product_id: str
    variant_id: str
    title: str
    quantity: int
    unit_price_cents: int
    currency: str
    thumbnail: str
    is_demo: bool = True

    @property
    def subtotal_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass(frozen=True)
class Cart:
    cart_id: str
    session_key: str
    status: str
    items: tuple[CartItem, ...]
    currency: str = "BRL"
    is_demo: bool = True

    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items)

    @property
    def total_cents(self) -> int:
        return sum(item.subtotal_cents for item in self.items)

    @property
    def empty(self) -> bool:
        return not self.items
