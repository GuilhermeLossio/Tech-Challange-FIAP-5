from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckoutSession:
    checkout_id: str
    cart_id: str
    user_id: str
    status: str
    total_cents: int
    currency: str
    idempotency_key: str
    correlation_id: str
    is_demo: bool = True
