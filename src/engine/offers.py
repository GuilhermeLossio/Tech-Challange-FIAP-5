from __future__ import annotations

from src.bandits import ACTIONS


OFFER_TO_ACTION = {
    "mens_email": "mens_email",
    "womens_email": "womens_email",
    "no_email": "no_email",
    "cashback_recurring_purchase": "womens_email",
    "savings_goal": "mens_email",
    "financial_education": "no_email",
    "account_upgrade": "mens_email",
    "installment_education": "no_email",
    "credit_limit": "mens_email",
    "personal_loan": "womens_email",
    "cashback_investment": "no_email",
}


def resolve_offer_action(offer_id: str) -> str:
    try:
        return OFFER_TO_ACTION[offer_id]
    except KeyError as error:
        raise ValueError(f"Unknown offer identifier: {offer_id}") from error


def known_offers() -> tuple[str, ...]:
    return tuple(OFFER_TO_ACTION)


def is_policy_action(action: str) -> bool:
    return action in ACTIONS
