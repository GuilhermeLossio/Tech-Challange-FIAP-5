from __future__ import annotations

import copy
import secrets
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import wraps
from threading import RLock
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from src.core.config import Settings
from src.demo.ecloe_pay.personas import external_user_id, persona_for_subject
from src.demo.ecloe_pay.repositories.base import (
    DEMO_CONFIRMATION_CODE,
    DEMO_USER_DISPLAY_NAME,
    DEMO_USER_PERSONA_LABEL,
    AuthSession,
    DemoSession,
    DemoUser,
    LoanRequest,
    OidcLoginFlow,
    PaymentOrder,
    PayRepository,
    SignupEmailAlreadyExists,
    SyntheticAccount,
    SyntheticProfile,
    WalletPayment,
    WalletSnapshot,
    WalletTransaction,
    account_with_initial_balance,
    demo_identity_emails,
    initial_loan_requests,
    initial_session,
    normalize_email,
    reward_payload,
    token_hash,
    user_id_for_email,
)


def _synchronized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class MemoryPayRepository(PayRepository):
    requires_authentication = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users: dict[str, tuple[DemoUser, str]] = {}
        self.auth_sessions: dict[str, AuthSession] = {}
        self.oidc_flows: dict[str, OidcLoginFlow] = {}
        self.external_identities: dict[tuple[str, str], str] = {}
        self.profiles: dict[str, SyntheticProfile] = {}
        self.accounts: dict[str, SyntheticAccount] = {}
        self.audit_events: list[dict[str, Any]] = []
        self.signup_registrations: list[dict[str, Any]] = []
        self.consent_acceptances: set[tuple[str, str, str]] = set()
        self.demo_sessions: dict[str, DemoSession] = {}
        self.benefit_events: dict[str, list[dict[str, Any]]] = {}
        self.outbox_events: list[dict[str, Any]] = []
        self.wallet_payments: dict[str, WalletPayment] = {}
        self.loan_request_rows: dict[str, tuple[LoanRequest, ...]] = {}
        self._lock = RLock()
        self._seed_user()

    def _seed_user(self) -> None:
        password_hash = generate_password_hash(self.settings.ecloe_pay_demo_user_password)
        for email in demo_identity_emails(self.settings.ecloe_pay_demo_user_email):
            self.create_or_update_demo_user(email, password_hash)

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
            display_name=DEMO_USER_DISPLAY_NAME,
            persona_label=DEMO_USER_PERSONA_LABEL,
        )
        self.users[user.user_id] = (user, password_hash)
        if user.user_id not in self.accounts:
            persona = persona_for_subject(user.user_id)
            self.profiles[user.user_id] = persona.profile
            self.accounts[user.user_id] = account_with_initial_balance(
                persona.account,
                self.settings.ecloe_pay_initial_balance_cents,
            )
        self.loan_request_rows.setdefault(user.user_id, initial_loan_requests(user.user_id))
        return user

    def authenticate(self, email: str, password: str) -> DemoUser | None:
        from src.demo.ecloe_pay.repositories.base import DUMMY_PASSWORD_HASH

        user = self.get_user_by_email(email)
        if user is None:
            check_password_hash(DUMMY_PASSWORD_HASH, password)
            return None
        _, password_hash = self.users[user.user_id]
        return user if check_password_hash(password_hash, password) else None

    def register_local_user(
        self,
        email: str,
        password_hash: str,
        *,
        signup_ip_hash: str,
        allow_ip_reuse: bool = False,
    ) -> DemoUser:
        email_normalized = normalize_email(email)
        if self.get_user_by_email(email_normalized) is not None:
            self.record_audit_event(None, "signup_duplicate_email", "blocked")
            raise SignupEmailAlreadyExists("An account already exists for this e-mail.")
        user = DemoUser(
            user_id=user_id_for_email(email_normalized),
            email=email_normalized,
            display_name=DEMO_USER_DISPLAY_NAME,
            persona_label=DEMO_USER_PERSONA_LABEL,
            auth_provider="local_signup",
        )
        self.users[user.user_id] = (user, password_hash)
        persona = persona_for_subject(user.user_id)
        self.profiles[user.user_id] = persona.profile
        self.accounts[user.user_id] = account_with_initial_balance(
            persona.account,
            self.settings.ecloe_pay_initial_balance_cents,
        )
        self.loan_request_rows[user.user_id] = initial_loan_requests(user.user_id)
        self.signup_registrations.append(
            {
                "ip_hash": signup_ip_hash,
                "user_id": user.user_id,
                "provider": "local_signup",
                "issuer": "ecloe.local",
                "subject_key": user.user_id,
                "result": "success",
                "created_at": datetime.now(UTC),
            }
        )
        self.record_audit_event(user.user_id, "signup_allowed", "success")
        self.record_audit_event(user.user_id, "account_provisioned", "success")
        return user

    def create_auth_session(self, user_id: str) -> AuthSession:
        now = datetime.now(UTC)
        auth_session = AuthSession(
            auth_session_id=f"paytok_{secrets.token_urlsafe(32)}",
            user_id=user_id,
            expires_at=now + timedelta(seconds=self.settings.ecloe_pay_session_ttl_seconds),
            idle_expires_at=now + timedelta(seconds=self.settings.ecloe_web_session_idle_seconds),
        )
        self.auth_sessions[token_hash(auth_session.auth_session_id)] = auth_session
        return auth_session

    def get_auth_session(self, auth_session_id: str) -> AuthSession | None:
        session = self.auth_sessions.get(token_hash(auth_session_id))
        if session is None or not session.active:
            return None
        session.idle_expires_at = datetime.now(UTC) + timedelta(
            seconds=self.settings.ecloe_web_session_idle_seconds
        )
        return session

    def revoke_auth_session(self, auth_session_id: str) -> None:
        stored_session = self.auth_sessions.get(token_hash(auth_session_id))
        if stored_session is not None:
            stored_session.revoked_at = datetime.now(UTC)

    def get_user(self, user_id: str) -> DemoUser | None:
        entry = self.users.get(user_id)
        return entry[0] if entry else None

    def store_oidc_flow(self, flow: OidcLoginFlow) -> None:
        self.oidc_flows[token_hash(flow.flow_id)] = flow

    def consume_oidc_flow(self, flow_id: str) -> OidcLoginFlow | None:
        flow = self.oidc_flows.pop(token_hash(flow_id), None)
        if flow is None or flow.expires_at <= datetime.now(UTC):
            return None
        return flow

    def provision_external_user(
        self,
        issuer: str,
        subject_key: str,
        *,
        signup_ip_hash: str | None = None,
        allow_ip_reuse: bool = False,
    ) -> DemoUser | None:
        identity_key = (issuer, subject_key)
        existing_user_id = self.external_identities.get(identity_key)
        if existing_user_id is not None:
            self.record_audit_event(existing_user_id, "signup_existing_identity", "success")
            return self.get_user(existing_user_id)
        persona = persona_for_subject(subject_key)
        user_id = external_user_id(subject_key)
        synthetic_email = f"{persona.persona_id}.{user_id[-8:]}@demo.ecloe.local"
        user = DemoUser(
            user_id=user_id,
            email=synthetic_email,
            display_name=persona.display_name,
            persona_label=persona.label,
            auth_provider="entra_external",
        )
        self.users[user_id] = (user, "")
        self.external_identities[identity_key] = user_id
        self.profiles[user_id] = persona.profile
        self.accounts[user_id] = account_with_initial_balance(
            persona.account,
            self.settings.ecloe_pay_initial_balance_cents,
        )
        self.loan_request_rows[user_id] = initial_loan_requests(user_id)
        if signup_ip_hash:
            self.signup_registrations.append(
                {
                    "ip_hash": signup_ip_hash,
                    "user_id": user_id,
                    "provider": "entra_external",
                    "issuer": issuer,
                    "subject_key": subject_key,
                    "result": "success",
                    "created_at": datetime.now(UTC),
                }
            )
        self.record_audit_event(user_id, "signup_allowed", "success")
        self.record_audit_event(user_id, "account_provisioned", "success")
        return user

    def synthetic_profile(self, user_id: str) -> SyntheticProfile | None:
        return self.profiles.get(user_id)

    def synthetic_account(self, user_id: str) -> SyntheticAccount | None:
        return self.accounts.get(user_id)

    def record_audit_event(self, user_id: str | None, event_type: str, result: str) -> None:
        self.audit_events.append(
            {
                "user_id": user_id,
                "event_type": event_type,
                "result": result,
                "occurred_at": datetime.now(UTC),
            }
        )

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

    def set_recommendation(
        self,
        session_id: str,
        decision_id: str,
        offer_id: str,
    ) -> DemoSession:
        session = self.demo_sessions[session_id]
        session.selected_decision_id = decision_id
        session.selected_offer_id = offer_id
        return session

    def wallet_snapshot(self, session_id: str) -> WalletSnapshot:
        session = self.demo_sessions.get(session_id)
        account = self.accounts.get(session.user_id) if session else None
        if account is None:
            return WalletSnapshot()
        return WalletSnapshot(
            demo_balance_cents=account.available_balance_cents,
            cashback_cents=account.cashback_cents,
            savings_goal_percent=account.savings_goal_percent,
            currency=account.currency,
        )

    def accept_terms(self, session_id: str) -> DemoSession:
        session = self.demo_sessions[session_id]
        session.terms_accepted = True
        self.consent_acceptances.add((session.user_id, "demo_terms", "2026-08"))
        return session

    @_synchronized
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

    def loan_requests(self, user_id: str) -> tuple[LoanRequest, ...]:
        return self.loan_request_rows.setdefault(user_id, initial_loan_requests(user_id))

    @_synchronized
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

    @_synchronized
    def pay_market_order(
        self,
        *,
        user_id: str,
        market_order_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
    ) -> WalletPayment:
        existing = self.wallet_payments.get(idempotency_key)
        if existing is not None:
            if (
                existing.user_id != user_id
                or existing.market_order_id != market_order_id
                or existing.amount_cents != amount_cents
                or existing.currency != currency
            ):
                raise ValueError("Wallet payment idempotency key belongs to another order.")
            return existing
        if amount_cents <= 0 or currency != "BRL":
            raise ValueError("The synthetic wallet payment amount is invalid.")
        account = self.accounts.get(user_id)
        if account is None or account.status != "active":
            raise ValueError("The ECloe Pay wallet is not active.")
        if account.available_balance_cents < amount_cents:
            raise ValueError("Insufficient ECloe Pay balance.")
        payment = WalletPayment(
            payment_id=f"wallet_payment_{uuid.uuid4().hex}",
            user_id=user_id,
            market_order_id=market_order_id,
            amount_cents=amount_cents,
            currency=currency,
            status="paid",
            balance_after_cents=account.available_balance_cents - amount_cents,
        )
        self.accounts[user_id] = replace(
            account,
            available_balance_cents=payment.balance_after_cents,
            transactions=(
                *account.transactions,
                WalletTransaction(
                    transaction_id=payment.payment_id,
                    description=f"ECloe Market order {market_order_id}",
                    amount_cents=-amount_cents,
                    category="market_purchase",
                    occurred_at=datetime.now(UTC).isoformat(),
                ),
            ),
        )
        self.wallet_payments[idempotency_key] = payment
        self._insert_outbox(
            "wallet_payment",
            payment.payment_id,
            "wallet_payment_paid",
            {"market_order_id": market_order_id, "amount_cents": amount_cents},
        )
        return payment

    def reset_demo_state(self, session_id: str) -> DemoSession:
        current = self.demo_sessions[session_id]
        for (_issuer, subject_key), user_id in self.external_identities.items():
            if user_id == current.user_id:
                persona = persona_for_subject(subject_key)
                self.profiles[user_id] = persona.profile
                self.accounts[user_id] = account_with_initial_balance(
                    persona.account,
                    self.settings.ecloe_pay_initial_balance_cents,
                )
                self.loan_request_rows[user_id] = initial_loan_requests(user_id)
                self.record_audit_event(user_id, "demo_reset", "success")
                break
        session = initial_session(current.user_id)
        self.demo_sessions[session.session_id] = session
        self.benefit_events[session.session_id] = []
        self.wallet_payments.clear()
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
