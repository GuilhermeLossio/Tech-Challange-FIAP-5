from __future__ import annotations

CONTEXT_COLUMNS = [
    "recency",
    "history_segment",
    "history",
    "zip_code",
    "newbie",
    "channel",
]

MODEL_CONTEXT_COLUMNS = [
    "recency",
    "history_segment",
    "newbie",
    "channel",
]

ACTION_COLUMN = "segment"

REWARD_COLUMNS = [
    "visit",
    "conversion",
    "spend",
]

BLOCKED_COLUMNS = [
    "customer_id",
    "name",
    "email",
    "phone",
    "gender",
    "sex",
    "sexo",
    "mens",
    "womens",
    "race",
    "income",
    "wealth",
    "zip_code",
    "history",
]

ALLOWED_ACTIONS = {
    "legacy_variant_a",
    "legacy_variant_b",
    "legacy_control",
}

REQUIRED_COLUMNS = [
    *CONTEXT_COLUMNS,
    ACTION_COLUMN,
    *REWARD_COLUMNS,
]
