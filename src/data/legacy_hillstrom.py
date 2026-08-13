from __future__ import annotations

from typing import Any

LEGACY_ACTIONS = ("legacy_variant_a", "legacy_variant_b", "legacy_control")

_SEGMENT_TO_ACTION = {
    "Mens E-Mail": "legacy_variant_a",
    "Womens E-Mail": "legacy_variant_b",
    "No E-Mail": "legacy_control",
}

_LEGACY_ID_TO_ACTION = {
    "mens_email": "legacy_variant_a",
    "womens_email": "legacy_variant_b",
    "no_email": "legacy_control",
}


def action_for_segment(segment: str) -> str | None:
    """Translate source campaign arms at the ingestion boundary only."""
    return _SEGMENT_TO_ACTION.get(segment)


def normalize_legacy_action(action: str) -> str:
    return _LEGACY_ID_TO_ACTION.get(action, action)


def migrate_legacy_action_rates(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    for field in ("action_rates",):
        values = migrated.get(field)
        if isinstance(values, dict):
            migrated[field] = {
                normalize_legacy_action(str(action)): stats for action, stats in values.items()
            }

    context_rates = migrated.get("context_rates")
    if isinstance(context_rates, dict):
        normalized_rates: dict[str, Any] = {}
        for key, stats in context_rates.items():
            normalized_key = str(key)
            normalized_stats = dict(stats) if isinstance(stats, dict) else stats
            for legacy, neutral in _LEGACY_ID_TO_ACTION.items():
                normalized_key = normalized_key.replace(f"action={legacy}", f"action={neutral}")
            if isinstance(normalized_stats, dict) and "action" in normalized_stats:
                normalized_stats["action"] = normalize_legacy_action(
                    str(normalized_stats["action"])
                )
            normalized_rates[normalized_key] = normalized_stats
        migrated["context_rates"] = normalized_rates
    return migrated
