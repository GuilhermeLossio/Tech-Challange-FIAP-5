from __future__ import annotations

import json
import secrets
import struct
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from werkzeug.security import check_password_hash

from src.core.config import Settings
from src.demo.ecloe_pay.repositories.base import (
    DEMO_CONFIRMATION_CODE,
    AuthSession,
    DemoSession,
    DemoUser,
    PaymentOrder,
    PayRepository,
    WalletSnapshot,
    aware_utc,
    initial_session,
    normalize_email,
    reward_payload,
    token_hash,
    user_id_for_email,
)


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

    def get_user_by_email(self, email: str) -> DemoUser | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT user_id, email_normalized AS email, display_name, persona_label
                    FROM ecloe_pay.demo_users
                    WHERE email_normalized = :email_normalized
                        AND is_active = 1
                        AND is_demo = 1
                        AND pii_allowed = 0
                    """
                ),
                {"email_normalized": normalize_email(email)},
            ).mappings().first()
        return DemoUser(**dict(row)) if row else None

    def create_or_update_demo_user(self, email: str, password_hash: str) -> DemoUser:
        from sqlalchemy import text

        email_normalized = normalize_email(email)
        user = DemoUser(
            user_id=user_id_for_email(email_normalized),
            email=email_normalized,
            display_name="ECloe Pay Demo Persona",
            persona_label="Synthetic wallet validation persona",
        )
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        """
                        IF NOT EXISTS (
                            SELECT 1 FROM ecloe_pay.demo_users WHERE email_normalized = :email_normalized
                        )
                        BEGIN
                            INSERT INTO ecloe_pay.demo_users (
                                user_id, email_normalized, display_name, persona_label, password_hash,
                                is_active, is_demo, pii_allowed
                            )
                            VALUES (
                                :user_id, :email_normalized, :display_name, :persona_label,
                                :password_hash, 1, 1, 0
                            )
                        END
                        ELSE
                        BEGIN
                            UPDATE ecloe_pay.demo_users
                            SET password_hash = :password_hash,
                                display_name = :display_name,
                                persona_label = :persona_label,
                                is_active = 1,
                                updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                            WHERE email_normalized = :email_normalized
                        END
                        """
                    ),
                    {**asdict(user), "email_normalized": email_normalized, "password_hash": password_hash},
                )
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()
        return user

    def authenticate(self, email: str, password: str) -> DemoUser | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        user_id,
                        email_normalized AS email,
                        password_hash,
                        display_name,
                        persona_label
                    FROM ecloe_pay.demo_users
                    WHERE email_normalized = :email_normalized
                        AND is_active = 1
                        AND is_demo = 1
                        AND pii_allowed = 0
                    """
                ),
                {"email_normalized": normalize_email(email)},
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

        raw_token = f"paytok_{secrets.token_urlsafe(32)}"
        auth_session = AuthSession(
            auth_session_id=raw_token,
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.settings.ecloe_pay_session_ttl_seconds),
        )
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        """
                        INSERT INTO ecloe_pay.auth_sessions (
                            auth_session_id, user_id, token_hash, expires_at
                        )
                        VALUES (
                            :auth_session_id, :user_id, :token_hash, :expires_at
                        )
                        """
                    ),
                    {
                        "auth_session_id": f"auth_{uuid.uuid4().hex}",
                        "user_id": user_id,
                        "token_hash": token_hash(raw_token),
                        "expires_at": auth_session.expires_at,
                    },
                )
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()
        return auth_session

    def get_auth_session(self, auth_session_id: str) -> AuthSession | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                row = connection.execute(
                    text(
                        """
                        SELECT auth_session_id, user_id, expires_at, revoked_at
                        FROM ecloe_pay.auth_sessions
                        WHERE token_hash = :token_hash
                        """
                    ),
                    {"token_hash": token_hash(auth_session_id)},
                ).mappings().first()
                if row is not None:
                    connection.execute(
                        text(
                            """
                            UPDATE ecloe_pay.auth_sessions
                            SET last_seen_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                            WHERE auth_session_id = :auth_session_id
                            """
                        ),
                        {"auth_session_id": row["auth_session_id"]},
                    )
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()
        if row is None:
            return None
        auth_session = AuthSession(
            auth_session_id=auth_session_id,
            user_id=row["user_id"],
            expires_at=aware_utc(row["expires_at"]),
            revoked_at=aware_utc(row["revoked_at"]) if row["revoked_at"] else None,
        )
        return auth_session if auth_session.active else None

    def revoke_auth_session(self, auth_session_id: str) -> None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        """
                        UPDATE ecloe_pay.auth_sessions
                        SET revoked_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                        WHERE token_hash = :token_hash
                        """
                    ),
                    {"token_hash": token_hash(auth_session_id)},
                )
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()

    def get_user(self, user_id: str) -> DemoUser | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT user_id, email_normalized AS email, display_name, persona_label
                    FROM ecloe_pay.demo_users
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).mappings().first()
        return DemoUser(**dict(row)) if row else None

    def get_or_create_demo_session(self, user_id: str) -> DemoSession:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                row = self._get_latest_session_row(connection, user_id)
                if row:
                    transaction.commit()
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
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()
        return session

    def get_demo_session(self, session_id: str) -> DemoSession | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(_DEMO_SESSION_QUERY + " WHERE ds.session_id = :session_id"),
                {"session_id": session_id},
            ).mappings().first()
        return _session_from_row(row) if row else None

    def wallet_snapshot(self, session_id: str) -> WalletSnapshot:
        from sqlalchemy import text

        with self.engine.connect() as connection:
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

        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text("UPDATE ecloe_pay.demo_sessions SET terms_accepted = 1 WHERE session_id = :session_id"),
                    {"session_id": session_id},
                )
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()
        session = self.get_demo_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def record_benefit_interaction(self, session_id: str, event_type: str, reward: float) -> dict[str, Any]:
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                payload = self._record_benefit_interaction(connection, session_id, event_type, reward)
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()
        return payload

    def get_payment_order(self, payment_order_id: str) -> PaymentOrder | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT payment_order_id, session_id, market_order_id, amount_cents,
                        currency, status, idempotency_key
                    FROM ecloe_pay.payment_orders
                    WHERE payment_order_id = :payment_order_id
                    """
                ),
                {"payment_order_id": payment_order_id},
            ).mappings().first()
        return PaymentOrder(**dict(row)) if row else None

    def simulate_payment(self, session_id: str, confirmation_code: str) -> tuple[str, dict[str, Any] | None]:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                session = connection.execute(
                    text(
                        _DEMO_SESSION_LOCK_QUERY
                        + """
                        WHERE ds.session_id = :session_id
                        """
                    ),
                    {"session_id": session_id},
                ).mappings().first()
                if session is None:
                    transaction.rollback()
                    raise KeyError(session_id)
                demo_session = _session_from_row(session)
                if not demo_session.terms_accepted:
                    transaction.rollback()
                    return "terms_required", None
                if confirmation_code != DEMO_CONFIRMATION_CODE:
                    result = connection.execute(
                        text(
                            """
                            UPDATE ecloe_pay.payment_orders
                            SET status = N'rejected',
                                updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                            WHERE payment_order_id = :payment_order_id
                                AND session_id = :session_id
                                AND status IN (N'created', N'rejected')
                            """
                        ),
                        {
                            "payment_order_id": demo_session.payment_order_id,
                            "session_id": session_id,
                        },
                    )
                    if result.rowcount != 1:
                        transaction.rollback()
                        return "duplicate", None
                    self._insert_outbox(
                        connection,
                        event_id=f"evt_pay_rejected_{uuid.uuid4().hex[:12]}",
                        aggregate_type="payment_order",
                        aggregate_id=demo_session.payment_order_id,
                        event_type="payment_rejected",
                        payload={"payment_order_id": demo_session.payment_order_id, "status": "rejected"},
                    )
                    transaction.commit()
                    return "rejected", None
                result = connection.execute(
                    text(
                        """
                        UPDATE ecloe_pay.payment_orders
                        SET status = N'verified',
                            updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                        WHERE payment_order_id = :payment_order_id
                            AND session_id = :session_id
                            AND status IN (N'created', N'rejected')
                        """
                    ),
                    {
                        "payment_order_id": demo_session.payment_order_id,
                        "session_id": session_id,
                    },
                )
                if result.rowcount != 1:
                    transaction.rollback()
                    return "duplicate", None
                payload = self._record_benefit_interaction(connection, session_id, "conversion", 1.0)
                self._insert_outbox(
                    connection,
                    event_id=f"evt_pay_verified_{uuid.uuid4().hex[:12]}",
                    aggregate_type="payment_order",
                    aggregate_id=demo_session.payment_order_id,
                    event_type="payment_verified",
                    payload=payload,
                )
            except Exception:
                if transaction.is_active:
                    transaction.rollback()
                raise
            else:
                if transaction.is_active:
                    transaction.commit()
        return "verified", payload

    def reset_demo_state(self, session_id: str) -> DemoSession:
        from sqlalchemy import text

        current = self.get_demo_session(session_id)
        if current is None:
            raise KeyError(session_id)
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
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
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()
        return self.get_or_create_demo_session(current.user_id)

    def reset_session(self, session_id: str) -> DemoSession:
        return self.reset_demo_state(session_id)

    def health_check(self) -> bool:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1

    def _get_latest_session_row(self, connection: Any, user_id: str) -> Any:
        from sqlalchemy import text

        return connection.execute(
            text(
                _DEMO_SESSION_QUERY
                + """
                WHERE ds.user_id = :user_id
                ORDER BY ds.created_at DESC
                """
            ),
            {"user_id": user_id},
        ).mappings().first()

    def _record_benefit_interaction(
        self,
        connection: Any,
        session_id: str,
        event_type: str,
        reward: float,
    ) -> dict[str, Any]:
        from sqlalchemy import text

        session_row = connection.execute(
            text(_DEMO_SESSION_QUERY + " WHERE ds.session_id = :session_id"),
            {"session_id": session_id},
        ).mappings().first()
        if session_row is None:
            raise KeyError(session_id)
        session = _session_from_row(session_row)
        event_id = f"evt_pay_demo_{uuid.uuid4().hex[:12]}"
        payload = reward_payload(session, event_id, event_type, reward)
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
        self._insert_outbox(connection, event_id, "benefit_interaction", event_id, event_type, payload)
        return payload

    def _insert_outbox(
        self,
        connection: Any,
        event_id: str,
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
                    outbox_event_id, event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at
                )
                VALUES (
                    :outbox_event_id, :event_id, :aggregate_type, :aggregate_id, :event_type,
                    :payload, :occurred_at
                )
                """
            ),
            {
                "outbox_event_id": f"out_{uuid.uuid4().hex}",
                "event_id": event_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "payload": json.dumps(payload),
                "occurred_at": datetime.now(UTC),
            },
        )


_DEMO_SESSION_QUERY = """
SELECT ds.session_id, ds.user_id, ds.demo_subject_key,
    ds.selected_decision_id, ds.selected_offer_id, ds.terms_accepted,
    po.payment_order_id, po.market_order_id, po.amount_cents,
    po.status, po.idempotency_key
FROM ecloe_pay.demo_sessions ds
JOIN ecloe_pay.payment_orders po ON po.session_id = ds.session_id
"""


_DEMO_SESSION_LOCK_QUERY = """
SELECT ds.session_id, ds.user_id, ds.demo_subject_key,
    ds.selected_decision_id, ds.selected_offer_id, ds.terms_accepted,
    po.payment_order_id, po.market_order_id, po.amount_cents,
    po.status, po.idempotency_key
FROM ecloe_pay.demo_sessions ds WITH (UPDLOCK, ROWLOCK)
JOIN ecloe_pay.payment_orders po WITH (UPDLOCK, ROWLOCK) ON po.session_id = ds.session_id
"""


def _session_from_row(row: Any) -> DemoSession:
    return DemoSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        demo_subject_key=row["demo_subject_key"],
        selected_decision_id=row["selected_decision_id"],
        selected_offer_id=row["selected_offer_id"],
        idempotency_key=row["idempotency_key"],
        bucket_name="ecloe-pay-demo-artifacts",
        payment_order_id=row["payment_order_id"],
        market_order_id=row["market_order_id"],
        payment_amount_cents=row["amount_cents"],
        payment_status=row["status"],
        terms_accepted=bool(row["terms_accepted"]),
    )
