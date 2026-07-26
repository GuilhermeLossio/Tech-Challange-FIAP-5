from __future__ import annotations

from src.engine.offers import known_offers
from src.engine.schemas import EngineRequest

ALLOWED_CONTEXT_FIELDS = {"channel", "history_segment", "newbie"}
ALLOWED_CHANNELS = {"Web", "Phone", "Multichannel"}
ALLOWED_NEWBIE_VALUES = {0, 1}
MAX_REQUEST_ID_LENGTH = 64
MAX_ELIGIBLE_OFFERS = 10


def validate_engine_request(request: EngineRequest) -> None:
    if not request.request_id:
        raise ValueError("request_id is required")
    if len(request.request_id) > MAX_REQUEST_ID_LENGTH:
        raise ValueError(f"request_id must contain at most {MAX_REQUEST_ID_LENGTH} characters")
    if not isinstance(request.customer_context, dict) or not request.customer_context:
        raise ValueError("customer_context is required")
    if not request.eligible_offers:
        raise ValueError("eligible_offers must contain at least one offer")
    if len(request.eligible_offers) > MAX_ELIGIBLE_OFFERS:
        raise ValueError(f"eligible_offers must contain at most {MAX_ELIGIBLE_OFFERS} offers")

    unknown_context_fields = sorted(set(request.customer_context) - ALLOWED_CONTEXT_FIELDS)
    if unknown_context_fields:
        raise ValueError(f"Unknown context fields are not allowed: {unknown_context_fields}")

    channel = request.customer_context.get("channel")
    if channel is not None and channel not in ALLOWED_CHANNELS:
        raise ValueError(f"Unsupported channel: {channel}")

    newbie = request.customer_context.get("newbie")
    if newbie is not None and newbie not in ALLOWED_NEWBIE_VALUES:
        raise ValueError(f"Unsupported newbie value: {newbie}")

    unknown_offers = sorted(set(request.eligible_offers) - set(known_offers()))
    if unknown_offers:
        raise ValueError(f"Unknown offer identifiers: {unknown_offers}")

    if len(request.eligible_offers) != len(set(request.eligible_offers)):
        raise ValueError("eligible_offers must not contain duplicate offers")
