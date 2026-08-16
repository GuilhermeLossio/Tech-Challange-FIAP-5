from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

COMMON_FEATURES = frozenset(
    {
        "surface",
        "decision_point",
        "channel",
        "newbie",
        "recency_band",
        "frequency_band",
        "history_segment",
    }
)
MARKET_FEATURES = frozenset(
    {
        "category_affinities",
        "cart_size_band",
        "cart_value_band",
    }
)
PAY_FEATURES = frozenset(
    {
        "wallet_engagement_band",
        "benefit_response_band",
        "savings_goal_active",
    }
)

BLOCKED_FEATURE_NAMES = frozenset(
    {
        "sex",
        "sexo",
        "gender",
        "genero",
        "mens",
        "womens",
        "race",
        "raca",
        "ethnicity",
        "religion",
        "health",
        "name",
        "email",
        "phone",
        "cpf",
        "address",
        "postal_code",
        "zip_code",
        "latitude",
        "longitude",
        "income",
        "wealth",
        "balance",
        "credit_score",
        "raw_history",
        "customer_id",
    }
)

_GENDERED_CATEGORY_TOKENS = frozenset(
    {"men", "mens", "male", "women", "womens", "female", "masculino", "feminino"}
)


def normalize_feature_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def assert_safe_payload(payload: Any, *, path: str = "payload") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = normalize_feature_name(str(key))
            if normalized in BLOCKED_FEATURE_NAMES:
                raise ValueError(f"Blocked decision feature: {path}.{key}")
            assert_safe_payload(value, path=f"{path}.{key}")
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, value in enumerate(payload):
            assert_safe_payload(value, path=f"{path}[{index}]")


def assert_allowed_context(context: Mapping[str, Any], surface: str) -> None:
    assert_safe_payload(context, path="customer_context")
    surface_features = MARKET_FEATURES if surface == "market" else PAY_FEATURES
    allowed = (COMMON_FEATURES | surface_features) - {"surface", "decision_point"}
    unknown = sorted(
        str(key) for key in context if normalize_feature_name(str(key)) not in allowed
    )
    if unknown:
        raise ValueError(f"Context contains non-allowlisted features for {surface}: {unknown}")


def neutralize_category(category: str) -> str:
    normalized = normalize_feature_name(category)
    tokens = set(normalized.split("_"))
    if tokens & _GENDERED_CATEGORY_TOKENS:
        return "apparel"
    return normalized or "uncategorized"
