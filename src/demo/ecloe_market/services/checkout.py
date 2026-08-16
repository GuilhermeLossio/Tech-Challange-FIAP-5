"""Checkout service boundary for price, stock, and item revalidation."""

from __future__ import annotations

from typing import Final

CHECKOUT_INVARIANTS: Final = (
    "revalidate_price",
    "revalidate_stock",
    "persist_order_and_items_atomically",
    "emit_outbox_after_commit",
)
