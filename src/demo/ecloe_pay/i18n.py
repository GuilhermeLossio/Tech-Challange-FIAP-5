from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import Request

DEFAULT_LOCALE = "en-US"
LOCALE_COOKIE_NAME = "ecloe_pay_locale"
SUPPORTED_LOCALES = ("pt-BR", "en-US")

I18N_DIR = Path(__file__).resolve().parent / "i18n"
MESSAGE_FILES = {
    "pt-BR": I18N_DIR / "pt-BR.json",
    "en-US": I18N_DIR / "en-US.json",
}


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().replace("_", "-").lower()
    if normalized.startswith("pt"):
        return "pt-BR"
    if normalized.startswith("en"):
        return "en-US"
    return normalized if normalized in SUPPORTED_LOCALES else None


def canonical_locale(value: str | None) -> str:
    return normalize_locale(value) or DEFAULT_LOCALE


def resolve_locale(request: Request) -> str:
    for candidate in [
        request.args.get("lang"),
        request.cookies.get(LOCALE_COOKIE_NAME),
    ]:
        locale = normalize_locale(candidate)
        if locale:
            return locale

    best_match = request.accept_languages.best_match(SUPPORTED_LOCALES)
    return normalize_locale(best_match) or DEFAULT_LOCALE


@lru_cache(maxsize=len(SUPPORTED_LOCALES))
def load_messages(locale: str) -> dict[str, Any]:
    effective_locale = normalize_locale(locale) or DEFAULT_LOCALE
    path = MESSAGE_FILES[effective_locale]
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    return data if isinstance(data, dict) else {}


def translate(messages: dict[str, Any], key: str) -> str:
    value: Any = messages
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return key
        value = value[part]
    return value if isinstance(value, str) else key
