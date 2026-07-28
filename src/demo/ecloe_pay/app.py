from __future__ import annotations

import hmac
import logging
import secrets
import time
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory

from src.core.config import Settings, load_settings
from src.demo.ecloe_pay.repositories import (
    PayRepository,
    create_pay_repository,
)

DEMO_DIR = Path(__file__).resolve().parent
AUTH_COOKIE_NAME = "ecloe_pay_session"
CSRF_COOKIE_NAME = "ecloe_pay_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
LOGIN_RATE_LIMIT_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 300
LOGGER = logging.getLogger(__name__)


def _cookie_secure(settings: Settings) -> bool:
    return settings.app_environment != "local"


def _set_auth_cookie(response, token: str, settings: Settings) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        httponly=True,
        secure=_cookie_secure(settings),
        samesite="Lax",
        path="/",
        max_age=settings.ecloe_pay_session_ttl_seconds,
    )


def _clear_auth_cookie(response, settings: Settings) -> None:
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        secure=_cookie_secure(settings),
        samesite="Lax",
        path="/",
    )


def _set_csrf_cookie(response, settings: Settings) -> str:
    token = request.cookies.get(CSRF_COOKIE_NAME) or secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        httponly=False,
        secure=_cookie_secure(settings),
        samesite="Lax",
        path="/",
        max_age=settings.ecloe_pay_session_ttl_seconds,
    )
    return token


def _csrf_valid() -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_token = request.headers.get(CSRF_HEADER_NAME, "")
    return bool(cookie_token and header_token) and hmac.compare_digest(cookie_token, header_token)


def _csrf_error():
    response = jsonify({"error": "Invalid ECloe Pay request token."})
    response.status_code = 403
    return response


def _auth_json(payload: dict[str, object], status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def _rate_limit_key(email: str) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded.split(",", 1)[0].strip() or request.remote_addr or "unknown"
    return f"{ip_address}:{email}"


def _login_rate_limited(app: Flask, email: str) -> bool:
    now = time.monotonic()
    attempts: dict[str, list[float]] = app.pay_login_attempts  # type: ignore[attr-defined]
    key = _rate_limit_key(email)
    recent = [stamp for stamp in attempts.get(key, []) if now - stamp < LOGIN_RATE_LIMIT_WINDOW_SECONDS]
    if len(recent) >= LOGIN_RATE_LIMIT_ATTEMPTS:
        attempts[key] = recent
        return True
    recent.append(now)
    attempts[key] = recent
    return False


def _clear_login_attempts(app: Flask, email: str) -> None:
    attempts: dict[str, list[float]] = app.pay_login_attempts  # type: ignore[attr-defined]
    attempts.pop(_rate_limit_key(email), None)


def _current_user(app: Flask) -> tuple[dict[str, object] | None, str | None]:
    repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
    auth_session_id = request.cookies.get(AUTH_COOKIE_NAME)
    if isinstance(auth_session_id, str):
        auth_session = repository.get_auth_session(auth_session_id)
        if auth_session is not None:
            user = repository.get_user(auth_session.user_id)
            if user is not None:
                return asdict(user), auth_session.user_id
    if not repository.requires_authentication:
        settings = app.pay_settings  # type: ignore[attr-defined]
        seeded = repository.get_user_by_email(settings.ecloe_pay_demo_user_email)
        if seeded is not None:
            return asdict(seeded), seeded.user_id
    return None, None


def _session_or_error(app: Flask):
    repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
    _, user_id = _current_user(app)
    if user_id is None:
        return None, jsonify({"error": "ECloe Pay login is required."}), 401
    demo_session = repository.get_or_create_demo_session(user_id)
    return demo_session, None, None


def create_app(
    settings: Settings | None = None,
    repository: PayRepository | None = None,
) -> Flask:
    settings = settings or load_settings(use_env_file=False)
    app = Flask(__name__, static_folder=str(DEMO_DIR), static_url_path="")
    app.config["JSON_SORT_KEYS"] = False
    app.secret_key = settings.subject_key_salt
    app.pay_settings = settings  # type: ignore[attr-defined]
    app.pay_repository = repository or create_pay_repository(settings)  # type: ignore[attr-defined]
    app.pay_login_attempts = {}  # type: ignore[attr-defined]

    @app.after_request
    def harden_auth_responses(response):
        if request.path.startswith("/api/auth/"):
            response.headers["Cache-Control"] = "no-store"
        if request.method == "GET" and request.path in {"/pay/login", "/pay"}:
            _set_csrf_cookie(response, settings)
        return response

    @app.get("/")
    def landing():
        return send_from_directory(DEMO_DIR, "landing.html")

    @app.get("/pay")
    def pay():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        if repository.requires_authentication:
            user, _ = _current_user(app)
            if user is None:
                return redirect("/pay/login")
        return send_from_directory(DEMO_DIR, "index.html")

    @app.get("/pay/login")
    def login_page():
        return send_from_directory(DEMO_DIR, "login.html")

    @app.post("/api/auth/login")
    def login():
        if not _csrf_valid():
            return _csrf_error()
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        if _login_rate_limited(app, email):
            LOGGER.info("ecloe_pay_login result=rate_limited")
            return _auth_json({"error": "Too many login attempts. Try again later."}, 429)
        user = repository.authenticate(email, password)
        if user is None:
            LOGGER.info("ecloe_pay_login result=invalid")
            return _auth_json({"error": "Invalid ECloe Pay demo credentials."}, 401)
        auth_session = repository.create_auth_session(user.user_id)
        repository.get_or_create_demo_session(user.user_id)
        _clear_login_attempts(app, email)
        response = _auth_json({"authenticated": True, "user": asdict(user)})
        _set_auth_cookie(response, auth_session.auth_session_id, settings)
        _set_csrf_cookie(response, settings)
        LOGGER.info("ecloe_pay_login user_id=%s result=success", user.user_id)
        return response

    @app.post("/api/auth/logout")
    def logout():
        if not _csrf_valid():
            return _csrf_error()
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        auth_session_id = request.cookies.get(AUTH_COOKIE_NAME)
        if isinstance(auth_session_id, str):
            repository.revoke_auth_session(auth_session_id)
        response = _auth_json({"authenticated": False})
        _clear_auth_cookie(response, settings)
        _set_csrf_cookie(response, settings)
        LOGGER.info("ecloe_pay_logout result=success")
        return response

    @app.get("/api/auth/me")
    def me():
        user, _ = _current_user(app)
        if user is None:
            return _auth_json({"authenticated": False}, 401)
        return _auth_json(
            {
                "authenticated": True,
                "user": user,
                "requires_authentication": app.pay_repository.requires_authentication,  # type: ignore[attr-defined]
            }
        )

    @app.get("/api/session")
    def get_session():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        wallet = repository.wallet_snapshot(demo_session.session_id)
        return jsonify(
            {
                "session": asdict(demo_session),
                "wallet": asdict(wallet),
                "benefit": {
                    "title": "Cashback for recurring purchases",
                    "message": "Earn cashback on your recurring purchases.",
                    "offer_id": demo_session.selected_offer_id,
                },
                "security": {
                    "user_creation_allowed": False,
                    "real_money_processed": False,
                    "requires_terms": True,
                    "bucket_name": demo_session.bucket_name,
                    "database_provider": "azure_sql" if repository.requires_authentication else "memory",
                    "database_schema": "ecloe_pay",
                },
            }
        )

    @app.post("/api/terms")
    def accept_terms():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        if not _csrf_valid():
            return _csrf_error()
        payload = request.get_json(silent=True) or {}
        if payload.get("accepted") is not True:
            return jsonify({"error": "Terms must be accepted before using ECloe Pay."}), 400
        demo_session = repository.accept_terms(demo_session.session_id)
        return jsonify({"accepted": True, "session_id": demo_session.session_id})

    @app.post("/api/benefit-interactions")
    def create_benefit_interaction():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        if not _csrf_valid():
            return _csrf_error()
        if not demo_session.terms_accepted:
            return jsonify({"error": "Demo terms are required before recording interactions."}), 403

        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip().lower()
        mapping = {
            "open": ("click", 0.2),
            "dismiss": ("dismissal", 0.0),
            "accept": ("conversion", 1.0),
        }
        if action not in mapping:
            return jsonify({"error": "Unsupported benefit action."}), 400

        event_type, reward = mapping[action]
        reward_event = repository.record_benefit_interaction(
            demo_session.session_id,
            event_type,
            reward,
        )
        return jsonify({"reward_event": reward_event, "engine_endpoint": "POST /v1/rewards"})

    @app.post("/api/payment-orders/<payment_order_id>/simulate")
    def simulate_payment(payment_order_id: str):
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        if not _csrf_valid():
            return _csrf_error()
        if not demo_session.terms_accepted:
            return jsonify({"error": "Demo terms are required before simulating payment."}), 403
        if payment_order_id != demo_session.payment_order_id:
            return jsonify({"error": "Payment order was not found in this demo session."}), 404

        payload = request.get_json(silent=True) or {}
        result, reward_event = repository.simulate_payment(
            demo_session.session_id,
            str(payload.get("confirmation_code", "")).strip(),
        )
        if result == "duplicate":
            return jsonify({"error": "Duplicate simulated payment blocked by idempotency."}), 409
        if result == "terms_required":
            return jsonify({"error": "Demo terms are required before simulating payment."}), 403
        if result == "rejected":
            return jsonify({"status": "rejected", "reason": "confirmation_code_mismatch"}), 400

        return jsonify(
            {
                "status": "verified",
                "payment_order": {
                    "payment_order_id": demo_session.payment_order_id,
                    "market_order_id": demo_session.market_order_id,
                    "amount_cents": demo_session.payment_amount_cents,
                    "currency": "BRL",
                    "idempotency_key": demo_session.idempotency_key,
                },
                "bucket_name": demo_session.bucket_name,
                "database_provider": "azure_sql" if repository.requires_authentication else "memory",
                "database_schema": "ecloe_pay",
                "reward_event": reward_event,
            }
        )

    @app.post("/api/reset")
    def reset_session():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        if not _csrf_valid():
            return _csrf_error()
        new_session = repository.reset_demo_state(demo_session.session_id)
        return jsonify({"reset": True, "session_id": new_session.session_id})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
