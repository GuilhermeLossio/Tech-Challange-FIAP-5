from __future__ import annotations

CONTEXT_COLUMNS = [
    "recency",
    "history_segment",
    "history",
    "mens",
    "womens",
    "zip_code",
    "newbie",
    "channel",
]

MODEL_CONTEXT_COLUMNS = [
    "recency",
    "history_segment",
    "mens",
    "womens",
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
    "race",
    "income",
    "wealth",
    "zip_code",
    "history",
]

ALLOWED_ACTIONS = {
    "mens_email",
    "womens_email",
    "no_email",
}

REQUIRED_COLUMNS = [
    *CONTEXT_COLUMNS,
    ACTION_COLUMN,
    *REWARD_COLUMNS,
]
