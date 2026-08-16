from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderItem:
    order_item_id: str
    order_id: str
    product_id: str
    variant_id: str
    title_snapshot: str
    quantity: int
    unit_price_cents: int
    currency: str
    is_demo: bool = True

    @property
    def subtotal_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass(frozen=True)
class Order:
    order_id: str
    checkout_id: str
    user_id: str
    status: str
    items: tuple[OrderItem, ...]
    total_cents: int
    currency: str
    is_demo: bool = True


@dataclass(frozen=True)
class PaymentReference:
    payment_reference_id: str
    order_id: str
    pay_payment_order_id: str
    status: str
    amount_cents: int
    currency: str
    is_demo: bool = True
