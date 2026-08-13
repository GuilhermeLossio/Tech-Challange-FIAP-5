from __future__ import annotations

from src.bandits import ACTIONS
from src.data.legacy_hillstrom import normalize_legacy_action

OFFER_TO_ACTION = {
    "cashback_recurring_purchase": "legacy_variant_b",
    "savings_goal": "legacy_variant_a",
    "financial_education": "legacy_control",
    "account_upgrade": "legacy_variant_a",
    "installment_education": "legacy_control",
    "credit_limit": "legacy_variant_a",
    "personal_loan": "legacy_variant_b",
    "cashback_investment": "legacy_control",
}


def resolve_offer_action(offer_id: str) -> str:
    try:
        return OFFER_TO_ACTION[offer_id]
    except KeyError as error:
        normalized = normalize_legacy_action(offer_id)
        if normalized in ACTIONS:
            return normalized
        raise ValueError(f"Unknown offer identifier: {offer_id}") from error


def known_offers() -> tuple[str, ...]:
    return tuple(OFFER_TO_ACTION)


def is_policy_action(action: str) -> bool:
    return action in ACTIONS
