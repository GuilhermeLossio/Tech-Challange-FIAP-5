from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

DEMO_DIR = Path(__file__).resolve().parent
DEMO_BUCKET_NAME = "ecloe-pay-demo-artifacts"
DEMO_CONFIRMATION_CODE = "0426"


@dataclass
class DemoSession:
    session_id: str
    demo_subject_key: str
    selected_decision_id: str
    selected_offer_id: str
    idempotency_key: str
    bucket_name: str
    payment_order_id: str
    market_order_id: str
    payment_amount_cents: int
    payment_status: str = "created"
    terms_accepted: bool = False


def _initial_session() -> DemoSession:
    return DemoSession(
        session_id="sess_pay_demo_001",
        demo_subject_key="demo-subject-pay-001",
        selected_decision_id="dec_demo_001",
        selected_offer_id="cashback_recurring_purchase",
        idempotency_key="pay-demo:order_demo_7841:0426",
        bucket_name=DEMO_BUCKET_NAME,
        payment_order_id="pay_order_demo_7841",
        market_order_id="order_demo_7841",
        payment_amount_cents=12790,
    )


def _event_payload(
    session: DemoSession,
    event_id: str,
    event_type: str,
    reward: float,
) -> dict[str, object]:
    return {
        "decision_id": session.selected_decision_id,
        "event_id": event_id,
        "event_type": event_type,
        "reward": reward,
        "occurred_at": datetime.now(UTC).isoformat(),
        "accepted": event_type == "conversion",
    }


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(DEMO_DIR), static_url_path="")
    app.config["JSON_SORT_KEYS"] = False
    app.demo_session = _initial_session()  # type: ignore[attr-defined]
    app.benefit_events = []  # type: ignore[attr-defined]

    @app.get("/")
    def landing():
        return send_from_directory(DEMO_DIR, "landing.html")

    @app.get("/pay")
    def pay():
        return send_from_directory(DEMO_DIR, "index.html")

    @app.get("/api/session")
    def get_session():
        session: DemoSession = app.demo_session  # type: ignore[attr-defined]
        return jsonify(
            {
                "session": asdict(session),
                "wallet": {
                    "demo_balance_cents": 42870,
                    "cashback_cents": 1840,
                    "savings_goal_percent": 64,
                    "currency": "BRL",
                },
                "benefit": {
                    "title": "Cashback for recurring purchases",
                    "message": "Earn cashback on your recurring purchases.",
                    "offer_id": session.selected_offer_id,
                },
                "security": {
                    "user_creation_allowed": False,
                    "real_money_processed": False,
                    "requires_terms": True,
                    "bucket_name": session.bucket_name,
                    "postgres_schema": "ecloe_pay",
                },
            }
        )

    @app.post("/api/terms")
    def accept_terms():
        payload = request.get_json(silent=True) or {}
        if payload.get("accepted") is not True:
            return jsonify({"error": "Terms must be accepted before using ECloe Pay."}), 400

        session: DemoSession = app.demo_session  # type: ignore[attr-defined]
        session.terms_accepted = True
        return jsonify({"accepted": True, "session_id": session.session_id})

    @app.post("/api/benefit-interactions")
    def create_benefit_interaction():
        session: DemoSession = app.demo_session  # type: ignore[attr-defined]
        if not session.terms_accepted:
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
        event_id = f"evt_pay_demo_{len(app.benefit_events) + 1:03d}"  # type: ignore[attr-defined]
        reward_payload = _event_payload(session, event_id, event_type, reward)
        app.benefit_events.append(reward_payload)  # type: ignore[attr-defined]
        return jsonify({"reward_event": reward_payload, "engine_endpoint": "POST /v1/rewards"})

    @app.post("/api/payment-orders/<payment_order_id>/simulate")
    def simulate_payment(payment_order_id: str):
        session: DemoSession = app.demo_session  # type: ignore[attr-defined]
        if not session.terms_accepted:
            return jsonify({"error": "Demo terms are required before simulating payment."}), 403
        if payment_order_id != session.payment_order_id:
            return jsonify({"error": "Payment order was not found in this demo session."}), 404
        if session.payment_status == "verified":
            return jsonify({"error": "Duplicate simulated payment blocked by idempotency."}), 409

        payload = request.get_json(silent=True) or {}
        if str(payload.get("confirmation_code", "")).strip() != DEMO_CONFIRMATION_CODE:
            session.payment_status = "rejected"
            return jsonify({"status": "rejected", "reason": "confirmation_code_mismatch"}), 400

        session.payment_status = "verified"
        event_id = f"evt_pay_demo_{len(app.benefit_events) + 1:03d}"  # type: ignore[attr-defined]
        reward_payload = _event_payload(session, event_id, "conversion", 1.0)
        app.benefit_events.append(reward_payload)  # type: ignore[attr-defined]
        return jsonify(
            {
                "status": "verified",
                "payment_order": {
                    "payment_order_id": session.payment_order_id,
                    "market_order_id": session.market_order_id,
                    "amount_cents": session.payment_amount_cents,
                    "currency": "BRL",
                    "idempotency_key": session.idempotency_key,
                },
                "bucket_name": session.bucket_name,
                "postgres_schema": "ecloe_pay",
                "reward_event": reward_payload,
            }
        )

    @app.post("/api/reset")
    def reset_session():
        app.demo_session = _initial_session()  # type: ignore[attr-defined]
        app.benefit_events = []  # type: ignore[attr-defined]
        return jsonify({"reset": True, "session_id": app.demo_session.session_id})  # type: ignore[attr-defined]

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
