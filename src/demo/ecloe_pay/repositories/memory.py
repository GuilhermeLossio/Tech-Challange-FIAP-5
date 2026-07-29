from __future__ import annotations

import copy
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from src.core.config import Settings
from src.demo.ecloe_pay.repositories.base import (
    DEMO_CONFIRMATION_CODE,
    AuthSession,
    DemoSession,
    DemoUser,
    PaymentOrder,
    PayRepository,
    WalletSnapshot,
    initial_session,
    normalize_email,
    reward_payload,
    token_hash,
    user_id_for_email,
)


class MemoryPayRepository(PayRepository):
    requires_authentication = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users: dict[str, tuple[DemoUser, str]] = {}
        self.auth_sessions: dict[str, AuthSession] = {}
        self.demo_sessions: dict[str, DemoSession] = {}
        self.benefit_events: dict[str, list[dict[str, Any]]] = {}
        self.outbox_events: list[dict[str, Any]] = []
        self._seed_user()

    def _seed_user(self) -> None:
        self.create_or_update_demo_user(
            self.settings.ecloe_pay_demo_user_email,
            generate_password_hash(self.settings.ecloe_pay_demo_user_password),
        )

    def get_user_by_email(self, email: str) -> DemoUser | None:
        email_normalized = normalize_email(email)
        for user, _ in self.users.values():
            if normalize_email(user.email) == email_normalized:
                return user
        return None

    def create_or_update_demo_user(self, email: str, password_hash: str) -> DemoUser:
        email_normalized = normalize_email(email)
        user = DemoUser(
            user_id=user_id_for_email(email_normalized),
            email=email_normalized,
            display_name="ECloe Pay Demo Persona",
            persona_label="Synthetic wallet validation persona",
        )
        self.users[user.user_id] = (user, password_hash)
        return user

    def authenticate(self, email: str, password: str) -> DemoUser | None:
        from src.demo.ecloe_pay.repositories.base import DUMMY_PASSWORD_HASH

        user = self.get_user_by_email(email)
        if user is None:
            check_password_hash(DUMMY_PASSWORD_HASH, password)
            return None
        _, password_hash = self.users[user.user_id]
        return user if check_password_hash(password_hash, password) else None

    def create_auth_session(self, user_id: str) -> AuthSession:
        auth_session = AuthSession(
            auth_session_id=f"paytok_{secrets.token_urlsafe(32)}",
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.settings.ecloe_pay_session_ttl_seconds),
        )
        self.auth_sessions[token_hash(auth_session.auth_session_id)] = auth_session
        return auth_session

    def get_auth_session(self, auth_session_id: str) -> AuthSession | None:
        session = self.auth_sessions.get(token_hash(auth_session_id))
        return session if session and session.active else None

    def revoke_auth_session(self, auth_session_id: str) -> None:
        stored_session = self.auth_sessions.get(token_hash(auth_session_id))
        if stored_session is not None:
            stored_session.revoked_at = datetime.now(UTC)

    def get_user(self, user_id: str) -> DemoUser | None:
        entry = self.users.get(user_id)
        return entry[0] if entry else None

    def get_or_create_demo_session(self, user_id: str) -> DemoSession:
        for session in self.demo_sessions.values():
            if session.user_id == user_id:
                return session
        session = initial_session(user_id)
        self.demo_sessions[session.session_id] = session
        self.benefit_events[session.session_id] = []
        return session

    def get_demo_session(self, session_id: str) -> DemoSession | None:
        return self.demo_sessions.get(session_id)

    def wallet_snapshot(self, session_id: str) -> WalletSnapshot:
        return WalletSnapshot()

    def accept_terms(self, session_id: str) -> DemoSession:
        session = self.demo_sessions[session_id]
        session.terms_accepted = True
        return session

    def record_benefit_interaction(self, session_id: str, event_type: str, reward: float) -> dict[str, Any]:
        session = self.demo_sessions[session_id]
        events = self.benefit_events.setdefault(session_id, [])
        event_id = f"evt_pay_demo_{len(events) + 1:03d}"
        payload = reward_payload(session, event_id, event_type, reward)
        events.append(payload)
        self._insert_outbox("benefit_interaction", event_id, event_type, payload)
        return payload

    def get_payment_order(self, payment_order_id: str) -> PaymentOrder | None:
        for session in self.demo_sessions.values():
            if session.payment_order_id == payment_order_id:
                return PaymentOrder(
                    payment_order_id=session.payment_order_id,
                    session_id=session.session_id,
                    market_order_id=session.market_order_id,
                    amount_cents=session.payment_amount_cents,
                    currency="BRL",
                    status=session.payment_status,
                    idempotency_key=session.idempotency_key,
                )
        return None

    def simulate_payment(self, session_id: str, confirmation_code: str) -> tuple[str, dict[str, Any] | None]:
        sessions_before = copy.deepcopy(self.demo_sessions)
        benefit_events_before = copy.deepcopy(self.benefit_events)
        outbox_events_before = copy.deepcopy(self.outbox_events)
        try:
            session = self.demo_sessions[session_id]
            if not session.terms_accepted:
                return "terms_required", None
            if confirmation_code != DEMO_CONFIRMATION_CODE:
                if session.payment_status != "verified":
                    session.payment_status = "rejected"
                    self._insert_outbox(
                        "payment_order",
                        session.payment_order_id,
                        "payment_rejected",
                        {"status": "rejected"},
                    )
                return "rejected", None
            if session.payment_status not in {"created", "rejected"}:
                return "duplicate", None
            session.payment_status = "verified"
            reward_event = self.record_benefit_interaction(session_id, "conversion", 1.0)
            self._insert_outbox("payment_order", session.payment_order_id, "payment_verified", reward_event)
            return "verified", reward_event
        except Exception:
            self.demo_sessions = sessions_before
            self.benefit_events = benefit_events_before
            self.outbox_events = outbox_events_before
            raise

    def reset_demo_state(self, session_id: str) -> DemoSession:
        current = self.demo_sessions[session_id]
        session = initial_session(current.user_id)
        self.demo_sessions[session.session_id] = session
        self.benefit_events[session.session_id] = []
        return session

    def reset_session(self, session_id: str) -> DemoSession:
        return self.reset_demo_state(session_id)

    def health_check(self) -> bool:
        return True

    def _insert_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self.outbox_events.append(
            {
                "outbox_event_id": f"out_{uuid.uuid4().hex}",
                "event_id": aggregate_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "payload": payload,
                "occurred_at": datetime.now(UTC),
            }
        )
