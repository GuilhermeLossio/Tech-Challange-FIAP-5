from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol

DEMO_BUCKET_NAME = "ecloe-pay-demo-artifacts"
DEMO_CONFIRMATION_CODE = "0426"
SHARED_DEMO_USER_EMAIL = "demo.market@ecloe.local"
LEGACY_PAY_DEMO_USER_EMAIL = "demo.pay@ecloe.local"
DEMO_USER_DISPLAY_NAME = "ECloe Demo Persona"
DEMO_USER_PERSONA_LABEL = "Synthetic marketplace-wallet validation persona"
DUMMY_PASSWORD_HASH = (
    "scrypt:32768:8:1$demoMissingPersonaSalt$"
    "8b8ab077e81740d9916f3cf5183f16bea14e97be7115cd89aa86f28ecb9156e4370d44"
    "fd99f74d07fbb47dfb453f23323d95ca0e1cf2cf3ec5931760949f8eb0"
)


@dataclass
class DemoUser:
    user_id: str
    email: str
    display_name: str
    persona_label: str
    auth_provider: str = "local"


@dataclass
class AuthSession:
    auth_session_id: str
    user_id: str
    expires_at: datetime
    revoked_at: datetime | None = None
    idle_expires_at: datetime | None = None

    @property
    def active(self) -> bool:
        now = datetime.now(UTC)
        return (
            self.revoked_at is None
            and self.expires_at > now
            and (self.idle_expires_at is None or self.idle_expires_at > now)
        )


@dataclass
class OidcLoginFlow:
    flow_id: str
    payload: dict[str, Any]
    return_to: str
    expires_at: datetime
    intent: str = "login"


@dataclass(frozen=True)
class SyntheticProfile:
    full_name: str
    city: str
    state_region: str
    preferred_language: str
    market_segment: str
    wallet_status: str = "active"


@dataclass(frozen=True)
class WalletTransaction:
    transaction_id: str
    description: str
    amount_cents: int
    category: str
    occurred_at: str


@dataclass(frozen=True)
class SyntheticAccount:
    available_balance_cents: int
    cashback_cents: int
    savings_goal_percent: int
    currency: str = "BRL"
    status: str = "active"
    transactions: tuple[WalletTransaction, ...] = field(default_factory=tuple)


@dataclass
class DemoSession:
    session_id: str
    user_id: str
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


@dataclass
class PaymentOrder:
    payment_order_id: str
    session_id: str
    market_order_id: str
    amount_cents: int
    currency: str
    status: str
    idempotency_key: str


@dataclass(frozen=True)
class LoanRequest:
    loan_request_id: str
    user_id: str
    requested_amount_cents: int
    currency: str
    status: str
    requested_at: str
    synthetic_notice: str = (
        "Synthetic ECloe Pay demo loan request. No credit decision, limit, score, or real loan is processed."
    )


@dataclass(frozen=True)
class WalletPayment:
    payment_id: str
    user_id: str
    market_order_id: str
    amount_cents: int
    currency: str
    status: str
    balance_after_cents: int


@dataclass
class WalletSnapshot:
    demo_balance_cents: int = 50000
    cashback_cents: int = 0
    savings_goal_percent: int = 0
    currency: str = "BRL"


class SignupIpLimitExceeded(ValueError):
    pass


class SignupEmailAlreadyExists(ValueError):
    pass


class PayRepository(Protocol):
    requires_authentication: bool

    def get_user_by_email(self, email: str) -> DemoUser | None:
        ...

    def create_or_update_demo_user(self, email: str, password_hash: str) -> DemoUser:
        ...

    def authenticate(self, email: str, password: str) -> DemoUser | None:
        ...

    def register_local_user(
        self,
        email: str,
        password_hash: str,
        *,
        signup_ip_hash: str,
        allow_ip_reuse: bool = False,
    ) -> DemoUser:
        ...

    def create_auth_session(self, user_id: str) -> AuthSession:
        ...

    def get_auth_session(self, auth_session_id: str) -> AuthSession | None:
        ...

    def revoke_auth_session(self, auth_session_id: str) -> None:
        ...

    def get_user(self, user_id: str) -> DemoUser | None:
        ...

    def store_oidc_flow(self, flow: OidcLoginFlow) -> None:
        ...

    def consume_oidc_flow(self, flow_id: str) -> OidcLoginFlow | None:
        ...

    def provision_external_user(
        self,
        issuer: str,
        subject_key: str,
        *,
        signup_ip_hash: str | None = None,
        allow_ip_reuse: bool = False,
    ) -> DemoUser | None:
        ...

    def synthetic_profile(self, user_id: str) -> SyntheticProfile | None:
        ...

    def synthetic_account(self, user_id: str) -> SyntheticAccount | None:
        ...

    def record_audit_event(self, user_id: str | None, event_type: str, result: str) -> None:
        ...

    def get_or_create_demo_session(self, user_id: str) -> DemoSession:
        ...

    def get_demo_session(self, session_id: str) -> DemoSession | None:
        ...

    def set_recommendation(
        self,
        session_id: str,
        decision_id: str,
        offer_id: str,
    ) -> DemoSession:
        ...

    def wallet_snapshot(self, session_id: str) -> WalletSnapshot:
        ...

    def accept_terms(self, session_id: str) -> DemoSession:
        ...

    def record_benefit_interaction(self, session_id: str, event_type: str, reward: float) -> dict[str, Any]:
        ...

    def get_payment_order(self, payment_order_id: str) -> PaymentOrder | None:
        ...

    def loan_requests(self, user_id: str) -> tuple[LoanRequest, ...]:
        ...

    def simulate_payment(self, session_id: str, confirmation_code: str) -> tuple[str, dict[str, Any] | None]:
        ...

    def pay_market_order(
        self,
        *,
        user_id: str,
        market_order_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
    ) -> WalletPayment:
        ...

    def reset_demo_state(self, session_id: str) -> DemoSession:
        ...

    def reset_session(self, session_id: str) -> DemoSession:
        ...

    def health_check(self) -> bool:
        ...


def normalize_email(email: str) -> str:
    return email.strip().lower()


def demo_identity_emails(configured_email: str) -> tuple[str, ...]:
    configured_normalized = normalize_email(configured_email)
    if configured_normalized in {SHARED_DEMO_USER_EMAIL, LEGACY_PAY_DEMO_USER_EMAIL}:
        emails = [
            configured_email,
            SHARED_DEMO_USER_EMAIL,
            LEGACY_PAY_DEMO_USER_EMAIL,
        ]
    else:
        emails = [configured_email]
    normalized = []
    for email in emails:
        email_normalized = normalize_email(email)
        if email_normalized and email_normalized not in normalized:
            normalized.append(email_normalized)
    return tuple(normalized)


def user_id_for_email(email: str) -> str:
    digest = hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()[:24]
    return f"user_demo_{digest}"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def account_with_initial_balance(account: SyntheticAccount, initial_balance_cents: int) -> SyntheticAccount:
    return replace(
        account,
        available_balance_cents=initial_balance_cents,
        cashback_cents=0,
        savings_goal_percent=0,
        transactions=(
            WalletTransaction(
                transaction_id="txn_opening_balance",
                description="Synthetic opening ECloe Pay balance",
                amount_cents=initial_balance_cents,
                category="opening_balance",
                occurred_at="2026-08-01T00:00:00+00:00",
            ),
        ),
    )


def initial_session(user_id: str) -> DemoSession:
    demo_suffix = user_id[-6:]
    if user_id == user_id_for_email(SHARED_DEMO_USER_EMAIL):
        market_order_id = "order_demo_7841"
        payment_order_id = "pay_order_demo_7841"
        idempotency_key = "pay-demo:order_demo_7841:0426"
    else:
        market_order_id = f"order_demo_7841_{demo_suffix}"
        payment_order_id = f"pay_order_demo_7841_{demo_suffix}"
        idempotency_key = f"pay-demo:{market_order_id}:0426"
    return DemoSession(
        session_id=f"sess_pay_demo_{demo_suffix}",
        user_id=user_id,
        demo_subject_key=f"demo-subject-pay-{demo_suffix}",
        selected_decision_id="",
        selected_offer_id="",
        idempotency_key=idempotency_key,
        bucket_name=DEMO_BUCKET_NAME,
        payment_order_id=payment_order_id,
        market_order_id=market_order_id,
        payment_amount_cents=12790,
    )


def initial_loan_requests(user_id: str) -> tuple[LoanRequest, ...]:
    digest = hashlib.sha256(f"loan-request\x00{user_id}".encode("utf-8")).hexdigest()
    amount_cents = 25000 + (int(digest[:4], 16) % 12) * 5000
    status = ("requested", "under_review", "cancelled")[int(digest[4:6], 16) % 3]
    return (
        LoanRequest(
            loan_request_id=f"loan_req_{digest[:16]}",
            user_id=user_id,
            requested_amount_cents=amount_cents,
            currency="BRL",
            status=status,
            requested_at="2026-08-01T12:00:00+00:00",
        ),
    )


def reward_payload(session: DemoSession, event_id: str, event_type: str, reward: float) -> dict[str, Any]:
    return {
        "decision_id": session.selected_decision_id,
        "event_id": event_id,
        "event_type": event_type,
        "reward": reward,
        "occurred_at": datetime.now(UTC).isoformat(),
        "accepted": event_type == "acceptance",
    }


def aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
