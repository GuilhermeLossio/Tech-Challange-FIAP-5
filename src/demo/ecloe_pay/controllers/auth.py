"""Authentication controller contract for the Flask Pay BFF."""

from __future__ import annotations

from typing import Final

AUTH_ROUTES: Final = ("/pay/login", "/auth/login", "/auth/signup", "/api/auth/login", "/api/auth/logout")
