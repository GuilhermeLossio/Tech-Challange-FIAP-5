from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session

from src.core.config import Settings, load_settings
from src.demo.ecloe_pay.repositories import (
    PayRepository,
    create_pay_repository,
)

DEMO_DIR = Path(__file__).resolve().parent


def _current_user(app: Flask) -> tuple[dict[str, object] | None, str | None]:
    repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
    auth_session_id = session.get("pay_auth_session_id")
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
    app.config["SESSION_COOKIE_SECURE"] = settings.ecloe_pay_cookie_secure
    app.config["PERMANENT_SESSION_LIFETIME"] = settings.ecloe_pay_session_ttl_seconds
    app.secret_key = settings.subject_key_salt
    app.pay_settings = settings  # type: ignore[attr-defined]
    app.pay_repository = repository or create_pay_repository(settings)  # type: ignore[attr-defined]

    @app.get("/")
    def landing():
        return send_from_directory(DEMO_DIR, "landing.html")

    @app.get("/pay")
    def pay():
        return send_from_directory(DEMO_DIR, "index.html")

    @app.get("/pay/login")
    def login_page():
        return send_from_directory(DEMO_DIR, "login.html")

    @app.post("/api/auth/login")
    def login():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip()
        password = str(payload.get("password", ""))
        user = repository.authenticate(email, password)
        if user is None:
            return jsonify({"error": "Invalid ECloe Pay demo credentials."}), 401
        auth_session = repository.create_auth_session(user.user_id)
        session.clear()
        session.permanent = True
        session["pay_auth_session_id"] = auth_session.auth_session_id
        repository.get_or_create_demo_session(user.user_id)
        return jsonify({"authenticated": True, "user": asdict(user)})

    @app.post("/api/auth/logout")
    def logout():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        auth_session_id = session.get("pay_auth_session_id")
        if isinstance(auth_session_id, str):
            repository.revoke_auth_session(auth_session_id)
        session.clear()
        return jsonify({"authenticated": False})

    @app.get("/api/auth/me")
    def me():
        user, _ = _current_user(app)
        if user is None:
            return jsonify({"authenticated": False}), 401
        return jsonify(
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
                    "sql_schema": "ecloe_pay",
                    "database_engine": "azure_sql"
                    if repository.requires_authentication
                    else "memory",
                },
            }
        )

    @app.post("/api/terms")
    def accept_terms():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
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
                "sql_schema": "ecloe_pay",
                "reward_event": reward_event,
            }
        )

    @app.post("/api/reset")
    def reset_session():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        new_session = repository.reset_demo_state(demo_session.session_id)
        return jsonify({"reset": True, "session_id": new_session.session_id})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
