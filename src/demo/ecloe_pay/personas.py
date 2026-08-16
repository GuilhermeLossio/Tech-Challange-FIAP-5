from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from src.demo.ecloe_pay.repositories.base import (
    SyntheticAccount,
    SyntheticProfile,
    WalletTransaction,
)

CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "demo" / "ecloe_user_personas.json"


@dataclass(frozen=True)
class Persona:
    persona_id: str
    display_name: str
    label: str
    profile: SyntheticProfile
    account: SyntheticAccount


def load_personas(path: Path = CATALOG_PATH) -> tuple[Persona, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    personas = []
    for item in payload["personas"]:
        account_data = dict(item["account"])
        transactions = tuple(WalletTransaction(**row) for row in account_data.pop("transactions"))
        personas.append(
            Persona(
                persona_id=item["persona_id"],
                display_name=item["display_name"],
                label=item["label"],
                profile=SyntheticProfile(**item["profile"]),
                account=SyntheticAccount(**account_data, transactions=transactions),
            )
        )
    if len(personas) < 4:
        raise ValueError("The synthetic persona catalog must contain at least four personas.")
    return tuple(personas)


def persona_for_subject(subject_key: str) -> Persona:
    personas = load_personas()
    index = int(hashlib.sha256(subject_key.encode("utf-8")).hexdigest(), 16) % len(personas)
    return personas[index]


def external_user_id(subject_key: str) -> str:
    return f"user_demo_{hashlib.sha256(subject_key.encode('utf-8')).hexdigest()[:24]}"
