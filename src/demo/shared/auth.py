from __future__ import annotations

from dataclasses import asdict
from typing import Any

from flask import Flask, Request

AUTH_COOKIE_NAME = "ecloe_pay_session"
CSRF_COOKIE_NAME = "ecloe_pay_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def current_user(app: Flask, request: Request) -> tuple[dict[str, Any] | None, str | None]:
    repository = app.pay_repository  # type: ignore[attr-defined]
    auth_session_id = request.cookies.get(AUTH_COOKIE_NAME)
    if isinstance(auth_session_id, str):
        auth_session = repository.get_auth_session(auth_session_id)
        if auth_session is not None:
            user = repository.get_user(auth_session.user_id)
            if user is not None:
                return asdict(user), auth_session.user_id
    return None, None
