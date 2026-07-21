from __future__ import annotations

from src.engine.offers import known_offers
from src.engine.schemas import EngineRequest


BLOCKED_CONTEXT_FIELDS = {
    "customer_id",
    "name",
    "email",
    "phone",
    "gender",
    "race",
    "income",
    "wealth",
    "zip_code",
    "history",
    "raw_purchase_history",
    "raw_basket",
    "credit_score",
}


def validate_engine_request(request: EngineRequest) -> None:
    if not request.request_id:
        raise ValueError("request_id is required")
    if not isinstance(request.customer_context, dict) or not request.customer_context:
        raise ValueError("customer_context is required")
    if not request.eligible_offers:
        raise ValueError("eligible_offers must contain at least one offer")

    blocked_fields = sorted(BLOCKED_CONTEXT_FIELDS & set(request.customer_context))
    if blocked_fields:
        raise ValueError(f"Blocked context fields are not allowed: {blocked_fields}")

    unknown_offers = sorted(set(request.eligible_offers) - set(known_offers()))
    if unknown_offers:
        raise ValueError(f"Unknown offer identifiers: {unknown_offers}")
