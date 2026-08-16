from __future__ import annotations

import hmac
import secrets
from typing import Any


def cookie_secure(app_environment: str) -> bool:
    return app_environment != "local"


def csrf_token(session: Any) -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str) or not token:
        token = secrets.token_hex(32)
        session["csrf_token"] = token
    return token


def rotate_csrf_token(session: Any) -> str:
    session.pop("csrf_token", None)
    return csrf_token(session)


def csrf_matches(cookie_token: str, header_token: str) -> bool:
    return bool(cookie_token and header_token) and hmac.compare_digest(cookie_token, header_token)
