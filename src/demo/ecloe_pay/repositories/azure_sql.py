from __future__ import annotations

import json
import secrets
import struct
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from werkzeug.security import check_password_hash

from src.core.config import Settings
from src.demo.ecloe_pay.personas import external_user_id, persona_for_subject
from src.demo.ecloe_pay.repositories.base import (
    DEMO_CONFIRMATION_CODE,
    DEMO_USER_DISPLAY_NAME,
    DEMO_USER_PERSONA_LABEL,
    DUMMY_PASSWORD_HASH,
    AuthSession,
    DemoSession,
    DemoUser,
    LoanRequest,
    OidcLoginFlow,
    PaymentOrder,
    PayRepository,
    SignupEmailAlreadyExists,
    SignupIpLimitExceeded,
    SyntheticAccount,
    SyntheticProfile,
    WalletPayment,
    WalletSnapshot,
    WalletTransaction,
    account_with_initial_balance,
    aware_utc,
    initial_loan_requests,
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
        engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        if "attrs_before" in connect_args:
            from sqlalchemy import event

            @event.listens_for(engine, "do_connect")
            def _remove_sqlalchemy_trusted_connection(dialect, connection_record, cargs, cparams):
                if cargs:
                    cargs[0] = cargs[0].replace(";Trusted_Connection=Yes", "")

        return engine

    @contextmanager
    def _transaction(self):
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                yield connection
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()

    def get_user_by_email(self, email: str) -> DemoUser | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT user_id, email_normalized AS email, display_name, persona_label, auth_provider
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
            display_name=DEMO_USER_DISPLAY_NAME,
            persona_label=DEMO_USER_PERSONA_LABEL,
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
                        persona_label,
                        auth_provider
                    FROM ecloe_pay.demo_users
                    WHERE email_normalized = :email_normalized
                        AND is_active = 1
                        AND is_demo = 1
                        AND pii_allowed = 0
                    """
                ),
                {"email_normalized": normalize_email(email)},
            ).mappings().first()
        if row is None or not row["password_hash"] or not check_password_hash(row["password_hash"], password):
            if row is None:
                check_password_hash(DUMMY_PASSWORD_HASH, password)
            return None
        return DemoUser(
            user_id=row["user_id"],
            email=row["email"],
            display_name=row["display_name"],
            persona_label=row["persona_label"],
            auth_provider=row["auth_provider"],
        )

    def register_local_user(
        self,
        email: str,
        password_hash: str,
        *,
        signup_ip_hash: str,
        allow_ip_reuse: bool = False,
    ) -> DemoUser:
        from sqlalchemy import text

        email_normalized = normalize_email(email)
        user_id = user_id_for_email(email_normalized)
        user = DemoUser(
            user_id=user_id,
            email=email_normalized,
            display_name=DEMO_USER_DISPLAY_NAME,
            persona_label=DEMO_USER_PERSONA_LABEL,
            auth_provider="local_signup",
        )
        persona = persona_for_subject(user_id)
        account = account_with_initial_balance(
            persona.account,
            self.settings.ecloe_pay_initial_balance_cents,
        )
        with self._transaction() as connection:
            existing = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM ecloe_pay.demo_users WITH (UPDLOCK, HOLDLOCK)
                    WHERE email_normalized = :email_normalized
                    """
                ),
                {"email_normalized": email_normalized},
            ).first()
            if existing is not None:
                self._record_audit(connection, None, "signup_duplicate_email", "blocked")
                raise SignupEmailAlreadyExists("An account already exists for this e-mail.")
            if not allow_ip_reuse:
                connection.execute(
                    text(
                        """
                        DECLARE @lock_result INT;
                        EXEC @lock_result = sp_getapplock
                            @Resource = :lock_resource,
                            @LockMode = 'Exclusive',
                            @LockOwner = 'Transaction',
                            @LockTimeout = 10000;
                        IF @lock_result < 0
                            THROW 51000, 'Could not acquire signup IP lock.', 1;
                        """
                    ),
                    {"lock_resource": f"ecloe_signup_ip:{signup_ip_hash}"},
                )
                successful_from_ip = connection.execute(
                    text(
                        """
                        SELECT COUNT_BIG(1)
                        FROM ecloe_pay.signup_registrations WITH (UPDLOCK, HOLDLOCK)
                        WHERE ip_hash = :ip_hash
                            AND result = N'success'
                        """
                    ),
                    {"ip_hash": signup_ip_hash},
                ).scalar_one()
                if int(successful_from_ip) >= self.settings.ecloe_signup_max_accounts_per_ip:
                    connection.execute(
                        text(
                            """
                            INSERT INTO ecloe_pay.signup_registrations (
                                registration_id, ip_hash, user_id, provider, issuer, subject_key, result
                            )
                            VALUES (
                                :registration_id, :ip_hash, NULL, N'local_signup',
                                N'ecloe.local', :subject_key, N'blocked_ip_limit'
                            )
                            """
                        ),
                        {
                            "registration_id": f"signup_{uuid.uuid4().hex}",
                            "ip_hash": signup_ip_hash,
                            "subject_key": user_id,
                        },
                    )
                    self._record_audit(connection, None, "signup_blocked_ip_limit", "blocked")
                    raise SignupIpLimitExceeded("Signup limit reached for this IP address.")
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.demo_users (
                        user_id, email_normalized, display_name, persona_label, password_hash,
                        auth_provider, is_active, is_demo, pii_allowed
                    )
                    VALUES (
                        :user_id, :email_normalized, :display_name, :persona_label,
                        :password_hash, N'local_signup', 1, 1, 0
                    )
                    """
                ),
                {
                    **asdict(user),
                    "email_normalized": email_normalized,
                    "password_hash": password_hash,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.demo_user_profiles (
                        user_id, full_name, address_line1, city, state_region, postal_code, country,
                        phone, preferred_language, market_segment, wallet_status
                    )
                    VALUES (
                        :user_id, :full_name, N'SYNTHETIC-NOT-COLLECTED', :city, :state_region,
                        N'DEMO', N'Brazil', N'DEMO', :preferred_language, :market_segment,
                        :wallet_status
                    )
                    """
                ),
                {**asdict(persona.profile), "user_id": user_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.wallet_accounts (
                        wallet_account_id, user_id, available_balance_cents, cashback_cents,
                        savings_goal_percent, currency, status
                    )
                    VALUES (
                        :wallet_account_id, :user_id, :available_balance_cents, :cashback_cents,
                        :savings_goal_percent, :currency, :status
                    )
                    """
                ),
                {**asdict(account), "wallet_account_id": f"wallet_{uuid.uuid4().hex}", "user_id": user_id},
            )
            for wallet_transaction in account.transactions:
                connection.execute(
                    text(
                        """
                        INSERT INTO ecloe_pay.wallet_transactions (
                            user_id, transaction_id, description, amount_cents, category, occurred_at
                        )
                        VALUES (
                            :user_id, :transaction_id, :description, :amount_cents, :category, :occurred_at
                        )
                        """
                    ),
                    {**asdict(wallet_transaction), "user_id": user_id},
                )
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.signup_registrations (
                        registration_id, ip_hash, user_id, provider, issuer, subject_key, result
                    )
                    VALUES (
                        :registration_id, :ip_hash, :user_id, N'local_signup',
                        N'ecloe.local', :subject_key, N'success'
                    )
                    """
                ),
                {
                    "registration_id": f"signup_{uuid.uuid4().hex}",
                    "ip_hash": signup_ip_hash,
                    "user_id": user_id,
                    "subject_key": user_id,
                },
            )
            self._record_audit(connection, user_id, "signup_allowed", "success")
            self._record_audit(connection, user_id, "account_provisioned", "success")
        return user

    def create_auth_session(self, user_id: str) -> AuthSession:
        from sqlalchemy import text

        raw_token = f"paytok_{secrets.token_urlsafe(32)}"
        now = datetime.now(UTC)
        auth_session = AuthSession(
            auth_session_id=raw_token,
            user_id=user_id,
            expires_at=now + timedelta(seconds=self.settings.ecloe_pay_session_ttl_seconds),
            idle_expires_at=now + timedelta(seconds=self.settings.ecloe_web_session_idle_seconds),
        )
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        """
                        INSERT INTO ecloe_pay.auth_sessions (
                            auth_session_id, user_id, token_hash, expires_at, idle_expires_at
                        )
                        VALUES (
                            :auth_session_id, :user_id, :token_hash, :expires_at, :idle_expires_at
                        )
                        """
                    ),
                    {
                        "auth_session_id": f"auth_{uuid.uuid4().hex}",
                        "user_id": user_id,
                        "token_hash": token_hash(raw_token),
                        "expires_at": auth_session.expires_at,
                        "idle_expires_at": auth_session.idle_expires_at,
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
                        SELECT auth_session_id, user_id, expires_at, revoked_at, idle_expires_at
                        FROM ecloe_pay.auth_sessions
                        WHERE token_hash = :token_hash
                        """
                    ),
                    {"token_hash": token_hash(auth_session_id)},
                ).mappings().first()
                now = datetime.now(UTC)
                if row is not None and row["revoked_at"] is None and aware_utc(row["expires_at"]) > now and aware_utc(row["idle_expires_at"]) > now:
                    connection.execute(
                        text(
                            """
                            UPDATE ecloe_pay.auth_sessions
                            SET last_seen_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00'),
                                idle_expires_at = :idle_expires_at
                            WHERE auth_session_id = :auth_session_id
                            """
                        ),
                        {
                            "auth_session_id": row["auth_session_id"],
                            "idle_expires_at": now
                            + timedelta(seconds=self.settings.ecloe_web_session_idle_seconds),
                        },
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
            idle_expires_at=aware_utc(row["idle_expires_at"]),
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
                    SELECT user_id, email_normalized AS email, display_name, persona_label, auth_provider
                    FROM ecloe_pay.demo_users
                    WHERE user_id = :user_id AND is_active = 1
                    """
                ),
                {"user_id": user_id},
            ).mappings().first()
        return DemoUser(**dict(row)) if row else None

    def store_oidc_flow(self, flow: OidcLoginFlow) -> None:
        from sqlalchemy import text

        with self._transaction() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM ecloe_pay.oidc_login_flows WHERE expires_at <= TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00');
                    INSERT INTO ecloe_pay.oidc_login_flows (
                        flow_id, token_hash, flow_payload, return_to, intent, expires_at
                    ) VALUES (:flow_id, :token_hash, :flow_payload, :return_to, :intent, :expires_at)
                    """
                ),
                {
                    "flow_id": f"flow_{uuid.uuid4().hex}",
                    "token_hash": token_hash(flow.flow_id),
                    "flow_payload": json.dumps(flow.payload),
                    "return_to": flow.return_to,
                    "intent": flow.intent,
                    "expires_at": flow.expires_at,
                },
            )

    def consume_oidc_flow(self, flow_id: str) -> OidcLoginFlow | None:
        from sqlalchemy import text

        with self._transaction() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT flow_id, flow_payload, return_to, intent, expires_at
                    FROM ecloe_pay.oidc_login_flows WITH (UPDLOCK, ROWLOCK)
                    WHERE token_hash = :token_hash
                    """
                ),
                {"token_hash": token_hash(flow_id)},
            ).mappings().first()
            if row is not None:
                connection.execute(
                    text("DELETE FROM ecloe_pay.oidc_login_flows WHERE flow_id = :flow_id"),
                    {"flow_id": row["flow_id"]},
                )
        if row is None or aware_utc(row["expires_at"]) <= datetime.now(UTC):
            return None
        return OidcLoginFlow(
            flow_id=flow_id,
            payload=json.loads(row["flow_payload"]),
            return_to=row["return_to"],
            expires_at=aware_utc(row["expires_at"]),
            intent=row.get("intent") or "login",
        )

    def provision_external_user(
        self,
        issuer: str,
        subject_key: str,
        *,
        signup_ip_hash: str | None = None,
        allow_ip_reuse: bool = False,
    ) -> DemoUser | None:
        from sqlalchemy import text

        persona = persona_for_subject(subject_key)
        account = account_with_initial_balance(
            persona.account,
            self.settings.ecloe_pay_initial_balance_cents,
        )
        user_id = external_user_id(subject_key)
        synthetic_email = f"{persona.persona_id}.{user_id[-8:]}@demo.ecloe.local"
        user = DemoUser(user_id, synthetic_email, persona.display_name, persona.label, "entra_external")
        with self._transaction() as connection:
            existing = connection.execute(
                text(
                    """
                    SELECT u.user_id, u.email_normalized AS email, u.display_name,
                        u.persona_label, u.auth_provider, u.is_active
                    FROM ecloe_pay.external_identities i
                    JOIN ecloe_pay.demo_users u ON u.user_id = i.user_id
                    WHERE i.provider = N'entra_external' AND i.issuer = :issuer
                        AND i.subject_key = :subject_key
                    """
                ),
                {"issuer": issuer, "subject_key": subject_key},
            ).mappings().first()
            if existing is not None:
                connection.execute(
                    text(
                        "UPDATE ecloe_pay.external_identities SET last_login_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00') WHERE provider = N'entra_external' AND issuer = :issuer AND subject_key = :subject_key"
                    ),
                    {"issuer": issuer, "subject_key": subject_key},
                )
                if not existing["is_active"]:
                    return None
                self._record_audit(connection, existing["user_id"], "signup_existing_identity", "success")
                return DemoUser(
                    existing["user_id"], existing["email"], existing["display_name"],
                    existing["persona_label"], existing["auth_provider"],
                )
            if signup_ip_hash and not allow_ip_reuse:
                connection.execute(
                    text(
                        """
                        DECLARE @lock_result INT;
                        EXEC @lock_result = sp_getapplock
                            @Resource = :lock_resource,
                            @LockMode = 'Exclusive',
                            @LockOwner = 'Transaction',
                            @LockTimeout = 10000;
                        IF @lock_result < 0
                            THROW 51000, 'Could not acquire signup IP lock.', 1;
                        """
                    ),
                    {"lock_resource": f"ecloe_signup_ip:{signup_ip_hash}"},
                )
                successful_from_ip = connection.execute(
                    text(
                        """
                        SELECT COUNT_BIG(1)
                        FROM ecloe_pay.signup_registrations WITH (UPDLOCK, HOLDLOCK)
                        WHERE ip_hash = :ip_hash AND result = N'success'
                        """
                    ),
                    {"ip_hash": signup_ip_hash},
                ).scalar_one()
                if int(successful_from_ip) >= self.settings.ecloe_signup_max_accounts_per_ip:
                    connection.execute(
                        text(
                            """
                            INSERT INTO ecloe_pay.signup_registrations (
                                registration_id, ip_hash, user_id, provider, issuer, subject_key, result
                            ) VALUES (
                                :registration_id, :ip_hash, NULL, N'entra_external', :issuer,
                                :subject_key, N'blocked_ip_limit'
                            )
                            """
                        ),
                        {
                            "registration_id": f"signup_{uuid.uuid4().hex}",
                            "ip_hash": signup_ip_hash,
                            "issuer": issuer,
                            "subject_key": subject_key,
                        },
                    )
                    self._record_audit(connection, None, "signup_blocked_ip_limit", "blocked")
                    raise SignupIpLimitExceeded("Signup limit reached for this IP address.")
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.demo_users (
                        user_id, email_normalized, display_name, persona_label, password_hash,
                        auth_provider, is_active, is_demo, pii_allowed, provisioning_version
                    ) VALUES (
                        :user_id, :email, :display_name, :persona_label, NULL,
                        N'entra_external', 1, 1, 0, 1
                    );
                    INSERT INTO ecloe_pay.external_identities (
                        identity_id, user_id, provider, issuer, subject_key, last_login_at
                    ) VALUES (
                        :identity_id, :user_id, N'entra_external', :issuer, :subject_key,
                        TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    );
                    INSERT INTO ecloe_pay.demo_user_profiles (
                        user_id, full_name, address_line1, city, state_region, postal_code,
                        country, phone, preferred_language, market_segment, wallet_status
                    ) VALUES (
                        :user_id, :full_name, N'SYNTHETIC-NOT-COLLECTED', :city, :state_region,
                        N'DEMO', N'Brazil', N'DEMO', :preferred_language, :market_segment, :wallet_status
                    );
                    INSERT INTO ecloe_pay.wallet_accounts (
                        wallet_account_id, user_id, available_balance_cents, cashback_cents,
                        savings_goal_percent, currency, status
                    ) VALUES (
                        :wallet_account_id, :user_id, :available_balance_cents, :cashback_cents,
                        :savings_goal_percent, :currency, :wallet_status
                    )
                    """
                ),
                {
                    **asdict(user),
                    **asdict(persona.profile),
                    "issuer": issuer,
                    "subject_key": subject_key,
                    "identity_id": f"identity_{uuid.uuid4().hex}",
                    "wallet_account_id": f"wallet_{uuid.uuid4().hex}",
                    "available_balance_cents": account.available_balance_cents,
                    "cashback_cents": account.cashback_cents,
                    "savings_goal_percent": account.savings_goal_percent,
                    "currency": account.currency,
                },
            )
            if signup_ip_hash:
                connection.execute(
                    text(
                        """
                        INSERT INTO ecloe_pay.signup_registrations (
                            registration_id, ip_hash, user_id, provider, issuer, subject_key, result
                        ) VALUES (
                            :registration_id, :ip_hash, :user_id, N'entra_external', :issuer,
                            :subject_key, N'success'
                        )
                        """
                    ),
                    {
                        "registration_id": f"signup_{uuid.uuid4().hex}",
                        "ip_hash": signup_ip_hash,
                        "user_id": user_id,
                        "issuer": issuer,
                        "subject_key": subject_key,
                    },
                )
            for transaction in account.transactions:
                connection.execute(
                    text(
                        """
                        INSERT INTO ecloe_pay.wallet_transactions (
                            transaction_id, user_id, description, amount_cents, category, occurred_at
                        ) VALUES (:transaction_id, :user_id, :description, :amount_cents, :category, :occurred_at)
                        """
                    ),
                    {**asdict(transaction), "user_id": user_id},
                )
            self._record_audit(connection, user_id, "signup_allowed", "success")
            self._record_audit(connection, user_id, "account_provisioned", "success")
        return user

    def synthetic_profile(self, user_id: str) -> SyntheticProfile | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT full_name, city, state_region, preferred_language, market_segment, wallet_status FROM ecloe_pay.demo_user_profiles WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            ).mappings().first()
        return SyntheticProfile(**dict(row)) if row else None

    def synthetic_account(self, user_id: str) -> SyntheticAccount | None:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            account = connection.execute(
                text(
                    "SELECT available_balance_cents, cashback_cents, savings_goal_percent, currency, status FROM ecloe_pay.wallet_accounts WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            ).mappings().first()
            rows = connection.execute(
                text(
                    "SELECT transaction_id, description, amount_cents, category, CONVERT(NVARCHAR(40), occurred_at, 127) AS occurred_at FROM ecloe_pay.wallet_transactions WHERE user_id = :user_id ORDER BY occurred_at DESC"
                ),
                {"user_id": user_id},
            ).mappings().all()
        if account is None:
            return None
        return SyntheticAccount(**dict(account), transactions=tuple(WalletTransaction(**dict(row)) for row in rows))

    def record_audit_event(self, user_id: str | None, event_type: str, result: str) -> None:
        with self._transaction() as connection:
            self._record_audit(connection, user_id, event_type, result)

    def _record_audit(self, connection: Any, user_id: str | None, event_type: str, result: str) -> None:
        from sqlalchemy import text

        connection.execute(
            text(
                "INSERT INTO ecloe_pay.security_audit_events (audit_event_id, user_id, event_type, result) VALUES (:audit_event_id, :user_id, :event_type, :result)"
            ),
            {"audit_event_id": f"audit_{uuid.uuid4().hex}", "user_id": user_id, "event_type": event_type, "result": result},
        )

    def get_or_create_demo_session(self, user_id: str) -> DemoSession:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                self._ensure_user_loan_requests(connection, user_id)
                row = self._get_latest_session_row(connection, user_id)
                if row:
                    transaction.commit()
                    return _session_from_row(row)
                session = initial_session(user_id)
                expires_at = datetime.now(UTC) + timedelta(hours=4)
                account = connection.execute(
                    text(
                        "SELECT available_balance_cents, cashback_cents, savings_goal_percent, currency FROM ecloe_pay.wallet_accounts WHERE user_id = :user_id"
                    ),
                    {"user_id": user_id},
                ).mappings().first()
                snapshot = dict(account) if account else asdict(WalletSnapshot())
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
                        VALUES (
                            :snapshot_id, :session_id, :demo_balance_cents, :cashback_cents,
                            :savings_goal_percent, :currency
                        )
                        """
                    ),
                    {
                        "snapshot_id": f"snap_{uuid.uuid4().hex}",
                        "session_id": session.session_id,
                        "demo_balance_cents": snapshot.get(
                            "demo_balance_cents", snapshot.get("available_balance_cents")
                        ),
                        "cashback_cents": snapshot["cashback_cents"],
                        "savings_goal_percent": snapshot["savings_goal_percent"],
                        "currency": snapshot["currency"],
                    },
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

    def set_recommendation(
        self,
        session_id: str,
        decision_id: str,
        offer_id: str,
    ) -> DemoSession:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                result = connection.execute(
                    text(
                        """
                        UPDATE ecloe_pay.demo_sessions
                        SET selected_decision_id = :decision_id,
                            selected_offer_id = :offer_id
                        WHERE session_id = :session_id
                        """
                    ),
                    {
                        "session_id": session_id,
                        "decision_id": decision_id,
                        "offer_id": offer_id,
                    },
                )
                if result.rowcount != 1:
                    raise KeyError(session_id)
                transaction.commit()
            except Exception:
                transaction.rollback()
                raise
        session = self.get_demo_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def wallet_snapshot(self, session_id: str) -> WalletSnapshot:
        from sqlalchemy import text

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT wa.available_balance_cents AS demo_balance_cents,
                        wa.cashback_cents, wa.savings_goal_percent, wa.currency
                    FROM ecloe_pay.demo_sessions ds
                    JOIN ecloe_pay.wallet_accounts wa ON wa.user_id = ds.user_id
                    WHERE ds.session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
            if row is None:
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
                connection.execute(
                    text(
                        """
                        IF NOT EXISTS (
                            SELECT 1 FROM ecloe_pay.consent_acceptances ca
                            JOIN ecloe_pay.demo_sessions ds ON ds.user_id = ca.user_id
                            WHERE ds.session_id = :session_id
                                AND ca.document_type = N'demo_terms'
                                AND ca.document_version = N'2026-08'
                        )
                        INSERT INTO ecloe_pay.consent_acceptances (
                            acceptance_id, user_id, document_type, document_version
                        )
                        SELECT :acceptance_id, user_id, N'demo_terms', N'2026-08'
                        FROM ecloe_pay.demo_sessions WHERE session_id = :session_id
                        """
                    ),
                    {"session_id": session_id, "acceptance_id": f"consent_{uuid.uuid4().hex}"},
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

    def loan_requests(self, user_id: str) -> tuple[LoanRequest, ...]:
        from sqlalchemy import text

        with self._transaction() as connection:
            self._ensure_user_loan_requests(connection, user_id)
            rows = connection.execute(
                text(
                    """
                    SELECT loan_request_id, user_id, requested_amount_cents, currency,
                        status, CONVERT(NVARCHAR(40), requested_at, 127) AS requested_at,
                        synthetic_notice
                    FROM ecloe_pay.loan_requests
                    WHERE user_id = :user_id
                    ORDER BY requested_at DESC, loan_request_id
                    """
                ),
                {"user_id": user_id},
            ).mappings().all()
        return tuple(LoanRequest(**dict(row)) for row in rows)

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

    def pay_market_order(
        self,
        *,
        user_id: str,
        market_order_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
    ) -> WalletPayment:
        from sqlalchemy import text

        if amount_cents <= 0 or currency != "BRL":
            raise ValueError("The synthetic wallet payment amount is invalid.")
        with self._transaction() as connection:
            existing = connection.execute(
                text(
                    """
                    SELECT payment_id, user_id, market_order_id, amount_cents, currency,
                        status, balance_after_cents
                    FROM ecloe_pay.wallet_payment_transactions
                    WHERE idempotency_key = :idempotency_key
                    """
                ),
                {"idempotency_key": idempotency_key},
            ).mappings().first()
            if existing is not None:
                if (
                    existing["user_id"] != user_id
                    or existing["market_order_id"] != market_order_id
                    or existing["amount_cents"] != amount_cents
                    or existing["currency"] != currency
                ):
                    raise ValueError("Wallet payment idempotency key belongs to another order.")
                return WalletPayment(**dict(existing))
            account = connection.execute(
                text(
                    """
                    SELECT available_balance_cents, currency, status
                    FROM ecloe_pay.wallet_accounts WITH (UPDLOCK, HOLDLOCK)
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).mappings().first()
            if account is None or account["status"] != "active":
                raise ValueError("The ECloe Pay wallet is not active.")
            if account["currency"] != currency:
                raise ValueError("The ECloe Pay wallet currency is not supported.")
            if account["available_balance_cents"] < amount_cents:
                raise ValueError("Insufficient ECloe Pay balance.")
            balance_after = account["available_balance_cents"] - amount_cents
            payment_id = f"wallet_payment_{uuid.uuid4().hex}"
            connection.execute(
                text(
                    """
                    UPDATE ecloe_pay.wallet_accounts
                    SET available_balance_cents = :balance_after,
                        updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id, "balance_after": balance_after},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.wallet_transactions
                        (user_id, transaction_id, description, amount_cents, category, occurred_at)
                    VALUES
                        (:user_id, :transaction_id, :description, :amount_cents, N'market_purchase',
                         TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00'))
                    """
                ),
                {
                    "user_id": user_id,
                    "transaction_id": payment_id,
                    "description": f"ECloe Market order {market_order_id}",
                    "amount_cents": -amount_cents,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ecloe_pay.wallet_payment_transactions (
                        payment_id, idempotency_key, user_id, market_order_id,
                        amount_cents, currency, status, balance_after_cents
                    ) VALUES (
                        :payment_id, :idempotency_key, :user_id, :market_order_id,
                        :amount_cents, :currency, N'paid', :balance_after
                    )
                    """
                ),
                {
                    "payment_id": payment_id,
                    "idempotency_key": idempotency_key,
                    "user_id": user_id,
                    "market_order_id": market_order_id,
                    "amount_cents": amount_cents,
                    "currency": currency,
                    "balance_after": balance_after,
                },
            )
        return WalletPayment(
            payment_id=payment_id,
            user_id=user_id,
            market_order_id=market_order_id,
            amount_cents=amount_cents,
            currency=currency,
            status="paid",
            balance_after_cents=balance_after,
        )

    def reset_demo_state(self, session_id: str) -> DemoSession:
        from sqlalchemy import text

        current = self.get_demo_session(session_id)
        if current is None:
            raise KeyError(session_id)
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                identity = connection.execute(
                    text(
                        "SELECT subject_key FROM ecloe_pay.external_identities WHERE user_id = :user_id AND provider = N'entra_external'"
                    ),
                    {"user_id": current.user_id},
                ).mappings().first()
                if identity is not None:
                    persona = persona_for_subject(identity["subject_key"])
                    account = account_with_initial_balance(
                        persona.account,
                        self.settings.ecloe_pay_initial_balance_cents,
                    )
                    connection.execute(
                        text(
                            """
                            UPDATE ecloe_pay.demo_user_profiles SET
                                full_name = :full_name, city = :city, state_region = :state_region,
                                preferred_language = :preferred_language, market_segment = :market_segment,
                                wallet_status = :wallet_status,
                                updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                            WHERE user_id = :user_id;
                            UPDATE ecloe_pay.wallet_accounts SET
                                available_balance_cents = :available_balance_cents,
                                cashback_cents = :cashback_cents,
                                savings_goal_percent = :savings_goal_percent,
                                currency = :currency, status = :wallet_status,
                                updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                            WHERE user_id = :user_id;
                            DELETE FROM ecloe_pay.wallet_transactions WHERE user_id = :user_id;
                            """
                        ),
                        {
                            **asdict(persona.profile),
                            "user_id": current.user_id,
                            "available_balance_cents": account.available_balance_cents,
                            "cashback_cents": account.cashback_cents,
                            "savings_goal_percent": account.savings_goal_percent,
                            "currency": account.currency,
                        },
                    )
                    for wallet_transaction in account.transactions:
                        connection.execute(
                            text(
                                "INSERT INTO ecloe_pay.wallet_transactions (user_id, transaction_id, description, amount_cents, category, occurred_at) VALUES (:user_id, :transaction_id, :description, :amount_cents, :category, :occurred_at)"
                            ),
                            {**asdict(wallet_transaction), "user_id": current.user_id},
                        )
                    self._record_audit(connection, current.user_id, "demo_reset", "success")
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

    def _ensure_user_loan_requests(self, connection: Any, user_id: str) -> None:
        from sqlalchemy import text

        for loan_request in initial_loan_requests(user_id):
            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM ecloe_pay.loan_requests
                        WHERE loan_request_id = :loan_request_id
                    )
                    INSERT INTO ecloe_pay.loan_requests (
                        loan_request_id, user_id, requested_amount_cents, currency,
                        status, requested_at, synthetic_notice
                    )
                    VALUES (
                        :loan_request_id, :user_id, :requested_amount_cents, :currency,
                        :status, :requested_at, :synthetic_notice
                    )
                    """
                ),
                asdict(loan_request),
            )

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
