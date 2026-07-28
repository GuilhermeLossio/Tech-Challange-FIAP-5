from __future__ import annotations

import hashlib
import json
import struct
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from src.core.config import Settings

DEMO_BUCKET_NAME = "ecloe-pay-demo-artifacts"
DEMO_CONFIRMATION_CODE = "0426"


@dataclass
class DemoUser:
    user_id: str
    email: str
    display_name: str
    persona_label: str


@dataclass
class AuthSession:
    auth_session_id: str
    user_id: str
    expires_at: datetime
    revoked_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.now(UTC)


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
class WalletSnapshot:
    demo_balance_cents: int = 42870
    cashback_cents: int = 1840
    savings_goal_percent: int = 64
    currency: str = "BRL"


class PayRepository:
    requires_authentication = False

    def authenticate(self, email: str, password: str) -> DemoUser | None:
        raise NotImplementedError

    def create_auth_session(self, user_id: str) -> AuthSession:
        raise NotImplementedError

    def get_auth_session(self, auth_session_id: str) -> AuthSession | None:
        raise NotImplementedError

    def revoke_auth_session(self, auth_session_id: str) -> None:
        raise NotImplementedError

    def get_user(self, user_id: str) -> DemoUser | None:
        raise NotImplementedError

    def get_or_create_demo_session(self, user_id: str) -> DemoSession:
        raise NotImplementedError

    def get_demo_session(self, session_id: str) -> DemoSession | None:
        raise NotImplementedError

    def wallet_snapshot(self, session_id: str) -> WalletSnapshot:
        raise NotImplementedError

    def accept_terms(self, session_id: str) -> DemoSession:
        raise NotImplementedError

    def record_benefit_interaction(self, session_id: str, event_type: str, reward: float) -> dict[str, Any]:
        raise NotImplementedError

    def simulate_payment(self, session_id: str, confirmation_code: str) -> tuple[str, dict[str, Any] | None]:
        raise NotImplementedError

    def reset_session(self, session_id: str) -> DemoSession:
        raise NotImplementedError


def user_id_for_email(email: str) -> str:
    digest = hashlib.sha256(email.lower().encode("utf-8")).hexdigest()[:24]
    return f"user_demo_{digest}"


def initial_session(user_id: str) -> DemoSession:
    return DemoSession(
        session_id=f"sess_pay_demo_{user_id[-6:]}",
        user_id=user_id,
        demo_subject_key=f"demo-subject-pay-{user_id[-6:]}",
        selected_decision_id="dec_demo_001",
        selected_offer_id="cashback_recurring_purchase",
        idempotency_key="pay-demo:order_demo_7841:0426",
        bucket_name=DEMO_BUCKET_NAME,
        payment_order_id="pay_order_demo_7841",
        market_order_id="order_demo_7841",
        payment_amount_cents=12790,
    )


def reward_payload(session: DemoSession, event_id: str, event_type: str, reward: float) -> dict[str, Any]:
    return {
        "decision_id": session.selected_decision_id,
        "event_id": event_id,
        "event_type": event_type,
        "reward": reward,
        "occurred_at": datetime.now(UTC).isoformat(),
        "accepted": event_type == "conversion",
    }


class MemoryPayRepository(PayRepository):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users: dict[str, tuple[DemoUser, str]] = {}
        self.auth_sessions: dict[str, AuthSession] = {}
        self.demo_sessions: dict[str, DemoSession] = {}
        self.benefit_events: dict[str, list[dict[str, Any]]] = {}
        self._seed_user()

    def _seed_user(self) -> None:
        email = self.settings.ecloe_pay_demo_user_email
        user = DemoUser(
            user_id=user_id_for_email(email),
            email=email,
            display_name="ECloe Pay Demo Persona",
            persona_label="Synthetic wallet validation persona",
        )
        self.users[user.user_id] = (
            user,
            generate_password_hash(self.settings.ecloe_pay_demo_user_password),
        )

    def authenticate(self, email: str, password: str) -> DemoUser | None:
        for user, password_hash in self.users.values():
            if user.email.lower() == email.lower() and check_password_hash(password_hash, password):
                return user
        return None

    def create_auth_session(self, user_id: str) -> AuthSession:
        auth_session = AuthSession(
            auth_session_id=f"auth_{uuid.uuid4().hex}",
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.settings.ecloe_pay_session_ttl_seconds),
        )
        self.auth_sessions[auth_session.auth_session_id] = auth_session
        return auth_session

    def get_auth_session(self, auth_session_id: str) -> AuthSession | None:
        session = self.auth_sessions.get(auth_session_id)
        return session if session and session.active else None

    def revoke_auth_session(self, auth_session_id: str) -> None:
        if auth_session_id in self.auth_sessions:
            self.auth_sessions[auth_session_id].revoked_at = datetime.now(UTC)

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
        return payload

    def simulate_payment(self, session_id: str, confirmation_code: str) -> tuple[str, dict[str, Any] | None]:
        session = self.demo_sessions[session_id]
        if session.payment_status == "verified":
            return "duplicate", None
        if confirmation_code != DEMO_CONFIRMATION_CODE:
            session.payment_status = "rejected"
            return "rejected", None
        session.payment_status = "verified"
        return "verified", self.record_benefit_interaction(session_id, "conversion", 1.0)

    def reset_session(self, session_id: str) -> DemoSession:
        current = self.demo_sessions[session_id]
        session = initial_session(current.user_id)
        self.demo_sessions[session.session_id] = session
        self.benefit_events[session.session_id] = []
        return session


class AzureSqlPayRepository(PayRepository):
    requires_authentication = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = self._create_engine()

    def _create_engine(self) -> Any:
        try:
            from sqlalchemy import URL, create_engine
        except ModuleNotFoundError as error:
            raise RuntimeError("Install the azure-sql extra to use ECLOE_PAY_DATABASE_MODE=azure_sql.") from error
        query = {
            "driver": self.settings.ecloe_pay_sql_driver,
            "Encrypt": "yes",
            "TrustServerCertificate": "no",
            "Connection Timeout": "30",
        }
        connect_args: dict[str, object] = {}
        if self.settings.ecloe_pay_sql_auth_mode == "entra_interactive":
            query["Authentication"] = "ActiveDirectoryInteractive"
        elif self.settings.ecloe_pay_sql_auth_mode == "managed_identity":
            query["Authentication"] = "ActiveDirectoryMsi"
        elif self.settings.ecloe_pay_sql_auth_mode == "azure_cli":
            try:
                from azure.identity import AzureCliCredential
            except ModuleNotFoundError as error:
                raise RuntimeError("azure-identity is required for ECLOE_PAY_SQL_AUTH_MODE=azure_cli.") from error
            token = AzureCliCredential().get_token("https://database.windows.net/.default").token
            token_bytes = token.encode("utf-16-le")
            connect_args["attrs_before"] = {
                1256: struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
            }
        url = URL.create(
            "mssql+pyodbc",
            host=self.settings.ecloe_pay_sql_server,
            database=self.settings.ecloe_pay_sql_database,
            query=query,
        )
        return create_engine(url, connect_args=connect_args, pool_pre_ping=True)

    def authenticate(self, email: str, password: str) -> DemoUser | None:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT user_id, email, password_hash, display_name, persona_label
                    FROM ecloe_pay.demo_users
                    WHERE LOWER(email) = LOWER(:email) AND pii_allowed = 0
                    """
                ),
                {"email": email},
            ).mappings().first()
        if row is None or not check_password_hash(row["password_hash"], password):
            return None
        return DemoUser(
            user_id=row["user_id"],
            email=row["email"],
            display_name=row["display_name"],
            persona_label=row["persona_label"],
        )

    def create_auth_session(self, user_id: str) -> AuthSession:
        from sqlalchemy import text

        auth_session = AuthSession(
            auth_session_id=f"auth_{uuid.uuid4().hex}",
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.settings.ecloe_pay_session_ttl_seconds),
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.auth_sessions (auth_session_id, user_id, expires_at)
                    VALUES (:auth_session_id, :user_id, :expires_at)
                    """
                ),
                asdict(auth_session),
            )
        return auth_session

    def get_auth_session(self, auth_session_id: str) -> AuthSession | None:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT auth_session_id, user_id, expires_at, revoked_at
                    FROM ecloe_pay.auth_sessions
                    WHERE auth_session_id = :auth_session_id
                    """
                ),
                {"auth_session_id": auth_session_id},
            ).mappings().first()
        if row is None:
            return None
        auth_session = AuthSession(
            auth_session_id=row["auth_session_id"],
            user_id=row["user_id"],
            expires_at=_aware(row["expires_at"]),
            revoked_at=_aware(row["revoked_at"]) if row["revoked_at"] else None,
        )
        return auth_session if auth_session.active else None

    def revoke_auth_session(self, auth_session_id: str) -> None:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE ecloe_pay.auth_sessions
                    SET revoked_at = SYSUTCDATETIME()
                    WHERE auth_session_id = :auth_session_id
                    """
                ),
                {"auth_session_id": auth_session_id},
            )

    def get_user(self, user_id: str) -> DemoUser | None:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT user_id, email, display_name, persona_label
                    FROM ecloe_pay.demo_users
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).mappings().first()
        return DemoUser(**dict(row)) if row else None

    def get_or_create_demo_session(self, user_id: str) -> DemoSession:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT TOP 1 ds.session_id, ds.user_id, ds.demo_subject_key,
                        ds.selected_decision_id, ds.selected_offer_id, ds.terms_accepted,
                        po.payment_order_id, po.market_order_id, po.amount_cents,
                        po.status, po.idempotency_key
                    FROM ecloe_pay.demo_sessions ds
                    JOIN ecloe_pay.payment_orders po ON po.session_id = ds.session_id
                    WHERE ds.user_id = :user_id
                    ORDER BY ds.created_at DESC
                    """
                ),
                {"user_id": user_id},
            ).mappings().first()
            if row:
                return _session_from_row(row)
            session = initial_session(user_id)
            expires_at = datetime.now(UTC) + timedelta(hours=4)
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.demo_sessions (
                        session_id, user_id, demo_subject_key, selected_decision_id,
                        selected_offer_id, expires_at
                    )
                    VALUES (
                        :session_id, :user_id, :demo_subject_key, :selected_decision_id,
                        :selected_offer_id, :expires_at
                    )
                    """
                ),
                {**asdict(session), "expires_at": expires_at},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.wallet_snapshots (
                        snapshot_id, session_id, demo_balance_cents, cashback_cents,
                        savings_goal_percent, currency
                    )
                    VALUES (:snapshot_id, :session_id, 42870, 1840, 64, 'BRL')
                    """
                ),
                {"snapshot_id": f"snap_{uuid.uuid4().hex}", "session_id": session.session_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.payment_orders (
                        payment_order_id, session_id, market_order_id, amount_cents,
                        status, idempotency_key
                    )
                    VALUES (
                        :payment_order_id, :session_id, :market_order_id, :payment_amount_cents,
                        :payment_status, :idempotency_key
                    )
                    """
                ),
                asdict(session),
            )
        return session

    def get_demo_session(self, session_id: str) -> DemoSession | None:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT ds.session_id, ds.user_id, ds.demo_subject_key,
                        ds.selected_decision_id, ds.selected_offer_id, ds.terms_accepted,
                        po.payment_order_id, po.market_order_id, po.amount_cents,
                        po.status, po.idempotency_key
                    FROM ecloe_pay.demo_sessions ds
                    JOIN ecloe_pay.payment_orders po ON po.session_id = ds.session_id
                    WHERE ds.session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
        return _session_from_row(row) if row else None

    def wallet_snapshot(self, session_id: str) -> WalletSnapshot:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT TOP 1 demo_balance_cents, cashback_cents, savings_goal_percent, currency
                    FROM ecloe_pay.wallet_snapshots
                    WHERE session_id = :session_id
                    ORDER BY created_at DESC
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
        return WalletSnapshot(**dict(row)) if row else WalletSnapshot()

    def accept_terms(self, session_id: str) -> DemoSession:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ecloe_pay.demo_sessions SET terms_accepted = 1 WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
        session = self.get_demo_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def record_benefit_interaction(self, session_id: str, event_type: str, reward: float) -> dict[str, Any]:
        from sqlalchemy import text

        session = self.get_demo_session(session_id)
        if session is None:
            raise KeyError(session_id)
        event_id = f"evt_pay_demo_{uuid.uuid4().hex[:12]}"
        payload = reward_payload(session, event_id, event_type, reward)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.benefit_interactions (
                        interaction_id, session_id, decision_id, offer_id, event_id,
                        event_type, reward, occurred_at
                    )
                    VALUES (
                        :interaction_id, :session_id, :decision_id, :offer_id, :event_id,
                        :event_type, :reward, :occurred_at
                    )
                    """
                ),
                {
                    "interaction_id": f"int_{uuid.uuid4().hex}",
                    "session_id": session_id,
                    "decision_id": session.selected_decision_id,
                    "offer_id": session.selected_offer_id,
                    "event_id": event_id,
                    "event_type": event_type,
                    "reward": reward,
                    "occurred_at": datetime.now(UTC),
                },
            )
            self._insert_outbox(connection, "benefit_interaction", event_id, event_type, payload)
        return payload

    def simulate_payment(self, session_id: str, confirmation_code: str) -> tuple[str, dict[str, Any] | None]:
        from sqlalchemy import text

        session = self.get_demo_session(session_id)
        if session is None:
            raise KeyError(session_id)
        if session.payment_status == "verified":
            return "duplicate", None
        if confirmation_code != DEMO_CONFIRMATION_CODE:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE ecloe_pay.payment_orders
                        SET status = N'rejected', updated_at = SYSUTCDATETIME()
                        WHERE payment_order_id = :payment_order_id
                        """
                    ),
                    {"payment_order_id": session.payment_order_id},
                )
            return "rejected", None
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE ecloe_pay.payment_orders
                    SET status = N'verified', updated_at = SYSUTCDATETIME()
                    WHERE payment_order_id = :payment_order_id AND status <> N'verified'
                    """
                ),
                {"payment_order_id": session.payment_order_id},
            )
        return "verified", self.record_benefit_interaction(session_id, "conversion", 1.0)

    def reset_session(self, session_id: str) -> DemoSession:
        from sqlalchemy import text

        current = self.get_demo_session(session_id)
        if current is None:
            raise KeyError(session_id)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM ecloe_pay.benefit_interactions WHERE session_id = :session_id;
                    DELETE FROM ecloe_pay.wallet_snapshots WHERE session_id = :session_id;
                    DELETE FROM ecloe_pay.payment_orders WHERE session_id = :session_id;
                    DELETE FROM ecloe_pay.demo_sessions WHERE session_id = :session_id;
                    """
                ),
                {"session_id": session_id},
            )
        return self.get_or_create_demo_session(current.user_id)

    def _insert_outbox(
        self,
        connection: Any,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        from sqlalchemy import text

        connection.execute(
            text(
                """
                INSERT INTO ecloe_pay.outbox_events (
                    outbox_event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at
                )
                VALUES (
                    :outbox_event_id, :aggregate_type, :aggregate_id, :event_type,
                    :payload, :occurred_at
                )
                """
            ),
            {
                "outbox_event_id": f"out_{uuid.uuid4().hex}",
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "payload": json.dumps(payload),
                "occurred_at": datetime.now(UTC),
            },
        )


def create_pay_repository(settings: Settings) -> PayRepository:
    if settings.ecloe_pay_database_mode == "memory":
        return MemoryPayRepository(settings)
    if settings.ecloe_pay_database_mode == "azure_sql":
        return AzureSqlPayRepository(settings)
    raise RuntimeError(f"Unsupported ECLOE_PAY_DATABASE_MODE: {settings.ecloe_pay_database_mode}")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _session_from_row(row: Any) -> DemoSession:
    return DemoSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        demo_subject_key=row["demo_subject_key"],
        selected_decision_id=row["selected_decision_id"],
        selected_offer_id=row["selected_offer_id"],
        idempotency_key=row["idempotency_key"],
        bucket_name=DEMO_BUCKET_NAME,
        payment_order_id=row["payment_order_id"],
        market_order_id=row["market_order_id"],
        payment_amount_cents=row["amount_cents"],
        payment_status=row["status"],
        terms_accepted=bool(row["terms_accepted"]),
    )
