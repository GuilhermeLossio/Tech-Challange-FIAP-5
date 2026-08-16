"""Payment controller contract for the Flask Pay BFF."""

from __future__ import annotations

from typing import Final

PAYMENT_ROUTES: Final = ("/api/payment-orders/<order_id>/simulate", "/api/reset")
