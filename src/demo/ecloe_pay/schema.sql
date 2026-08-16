IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ecloe_pay')
BEGIN
    EXEC(N'CREATE SCHEMA ecloe_pay');
END;
GO

IF OBJECT_ID(N'ecloe_pay.demo_users', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.demo_users (
        user_id NVARCHAR(64) NOT NULL CONSTRAINT pk_demo_users PRIMARY KEY,
        email_normalized NVARCHAR(254) MASKED WITH (FUNCTION = 'email()') NOT NULL,
        display_name NVARCHAR(120) NOT NULL,
        persona_label NVARCHAR(120) NOT NULL,
        password_hash NVARCHAR(512) NULL,
        auth_provider NVARCHAR(40) NOT NULL CONSTRAINT df_demo_users_auth_provider DEFAULT N'local',
        provisioning_version INT NOT NULL CONSTRAINT df_demo_users_provisioning_version DEFAULT 1,
        is_active BIT NOT NULL CONSTRAINT df_demo_users_is_active DEFAULT 1,
        is_demo BIT NOT NULL CONSTRAINT df_demo_users_is_demo DEFAULT 1,
        pii_allowed BIT NOT NULL CONSTRAINT df_demo_users_pii_allowed DEFAULT 0,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_demo_users_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_demo_users_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT uq_demo_users_email_normalized UNIQUE (email_normalized),
        CONSTRAINT ck_demo_users_is_demo CHECK (is_demo = 1),
        CONSTRAINT ck_demo_users_pii_allowed CHECK (pii_allowed = 0)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.masked_columns
    WHERE object_id = OBJECT_ID(N'ecloe_pay.demo_users')
        AND name = N'email_normalized'
        AND is_masked = 1
)
BEGIN
    ALTER TABLE ecloe_pay.demo_users
        ALTER COLUMN email_normalized ADD MASKED WITH (FUNCTION = 'email()');
END;
GO

IF OBJECT_ID(N'ecloe_pay.demo_user_profiles', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.demo_user_profiles (
        user_id NVARCHAR(64) NOT NULL CONSTRAINT pk_demo_user_profiles PRIMARY KEY,
        full_name NVARCHAR(160) MASKED WITH (FUNCTION = 'partial(2, "****", 1)') NOT NULL,
        address_line1 NVARCHAR(240) MASKED WITH (FUNCTION = 'partial(4, "****", 2)') NOT NULL,
        city NVARCHAR(120) NOT NULL,
        state_region NVARCHAR(120) NOT NULL,
        postal_code NVARCHAR(40) MASKED WITH (FUNCTION = 'partial(2, "****", 1)') NOT NULL,
        country NVARCHAR(80) NOT NULL,
        phone NVARCHAR(40) MASKED WITH (FUNCTION = 'partial(3, "****", 2)') NOT NULL,
        preferred_language NVARCHAR(12) NOT NULL,
        market_segment NVARCHAR(80) NOT NULL,
        wallet_status NVARCHAR(40) NOT NULL,
        masking_enabled BIT NOT NULL CONSTRAINT df_demo_user_profiles_masking_enabled DEFAULT 1,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_demo_user_profiles_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_demo_user_profiles_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_demo_user_profiles_demo_users
            FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
        CONSTRAINT ck_demo_user_profiles_masking_enabled CHECK (masking_enabled = 1),
        CONSTRAINT ck_demo_user_profiles_wallet_status CHECK (wallet_status IN (N'active', N'review', N'inactive')),
        CONSTRAINT ck_demo_user_profiles_preferred_language CHECK (preferred_language IN (N'pt-BR', N'en-US'))
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.masked_columns
    WHERE object_id = OBJECT_ID(N'ecloe_pay.demo_user_profiles')
        AND name = N'full_name'
        AND is_masked = 1
)
BEGIN
    ALTER TABLE ecloe_pay.demo_user_profiles
        ALTER COLUMN full_name ADD MASKED WITH (FUNCTION = 'partial(2, "****", 1)');
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.masked_columns
    WHERE object_id = OBJECT_ID(N'ecloe_pay.demo_user_profiles')
        AND name = N'address_line1'
        AND is_masked = 1
)
BEGIN
    ALTER TABLE ecloe_pay.demo_user_profiles
        ALTER COLUMN address_line1 ADD MASKED WITH (FUNCTION = 'partial(4, "****", 2)');
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.masked_columns
    WHERE object_id = OBJECT_ID(N'ecloe_pay.demo_user_profiles')
        AND name = N'postal_code'
        AND is_masked = 1
)
BEGIN
    ALTER TABLE ecloe_pay.demo_user_profiles
        ALTER COLUMN postal_code ADD MASKED WITH (FUNCTION = 'partial(2, "****", 1)');
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.masked_columns
    WHERE object_id = OBJECT_ID(N'ecloe_pay.demo_user_profiles')
        AND name = N'phone'
        AND is_masked = 1
)
BEGIN
    ALTER TABLE ecloe_pay.demo_user_profiles
        ALTER COLUMN phone ADD MASKED WITH (FUNCTION = 'partial(3, "****", 2)');
END;
GO

IF OBJECT_ID(N'ecloe_pay.auth_sessions', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.auth_sessions (
        auth_session_id NVARCHAR(64) NOT NULL CONSTRAINT pk_auth_sessions PRIMARY KEY,
        user_id NVARCHAR(64) NOT NULL,
        token_hash NVARCHAR(128) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_auth_sessions_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        expires_at DATETIMEOFFSET(7) NOT NULL,
        idle_expires_at DATETIMEOFFSET(7) NOT NULL,
        revoked_at DATETIMEOFFSET(7) NULL,
        last_seen_at DATETIMEOFFSET(7) NULL,
        CONSTRAINT fk_auth_sessions_demo_users
            FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
        CONSTRAINT uq_auth_sessions_token_hash UNIQUE (token_hash)
    );
END;
GO

IF OBJECT_ID(N'ecloe_pay.demo_sessions', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.demo_sessions (
        session_id NVARCHAR(64) NOT NULL CONSTRAINT pk_demo_sessions PRIMARY KEY,
        user_id NVARCHAR(64) NOT NULL,
        demo_subject_key NVARCHAR(120) NOT NULL,
        selected_decision_id NVARCHAR(80) NULL,
        selected_offer_id NVARCHAR(80) NULL,
        terms_accepted BIT NOT NULL CONSTRAINT df_demo_sessions_terms_accepted DEFAULT 0,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_demo_sessions_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        expires_at DATETIMEOFFSET(7) NOT NULL,
        locked_at DATETIMEOFFSET(7) NULL,
        CONSTRAINT fk_demo_sessions_demo_users
            FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
        CONSTRAINT ck_demo_sessions_session_id CHECK (session_id LIKE N'sess_%')
    );
END;
GO

IF OBJECT_ID(N'ecloe_pay.wallet_snapshots', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.wallet_snapshots (
        snapshot_id NVARCHAR(64) NOT NULL CONSTRAINT pk_wallet_snapshots PRIMARY KEY,
        session_id NVARCHAR(64) NOT NULL,
        demo_balance_cents INT NOT NULL,
        cashback_cents INT NOT NULL,
        savings_goal_percent INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_wallet_snapshots_currency DEFAULT 'BRL',
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_wallet_snapshots_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_wallet_snapshots_demo_sessions
            FOREIGN KEY (session_id) REFERENCES ecloe_pay.demo_sessions(session_id),
        CONSTRAINT ck_wallet_snapshots_demo_balance CHECK (demo_balance_cents >= 0),
        CONSTRAINT ck_wallet_snapshots_cashback CHECK (cashback_cents >= 0),
        CONSTRAINT ck_wallet_snapshots_savings_goal CHECK (savings_goal_percent BETWEEN 0 AND 100),
        CONSTRAINT ck_wallet_snapshots_currency CHECK (currency = 'BRL')
    );
END;
GO

IF OBJECT_ID(N'ecloe_pay.payment_orders', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.payment_orders (
        payment_order_id NVARCHAR(80) NOT NULL CONSTRAINT pk_payment_orders PRIMARY KEY,
        session_id NVARCHAR(64) NOT NULL,
        market_order_id NVARCHAR(80) NOT NULL,
        amount_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_payment_orders_currency DEFAULT 'BRL',
        status NVARCHAR(20) NOT NULL,
        idempotency_key NVARCHAR(160) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_payment_orders_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_payment_orders_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_payment_orders_demo_sessions
            FOREIGN KEY (session_id) REFERENCES ecloe_pay.demo_sessions(session_id),
        CONSTRAINT uq_payment_orders_idempotency_key UNIQUE (idempotency_key),
        CONSTRAINT ck_payment_orders_amount CHECK (amount_cents >= 0),
        CONSTRAINT ck_payment_orders_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_payment_orders_status CHECK (status IN (N'created', N'verified', N'rejected', N'cancelled'))
    );
END;
GO

IF OBJECT_ID(N'ecloe_pay.benefit_interactions', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.benefit_interactions (
        interaction_id NVARCHAR(80) NOT NULL CONSTRAINT pk_benefit_interactions PRIMARY KEY,
        session_id NVARCHAR(64) NOT NULL,
        decision_id NVARCHAR(80) NOT NULL,
        offer_id NVARCHAR(80) NOT NULL,
        event_id NVARCHAR(80) NOT NULL,
        event_type NVARCHAR(20) NOT NULL,
        reward DECIMAL(4, 2) NOT NULL,
        occurred_at DATETIMEOFFSET(7) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_benefit_interactions_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_benefit_interactions_demo_sessions
            FOREIGN KEY (session_id) REFERENCES ecloe_pay.demo_sessions(session_id),
        CONSTRAINT uq_benefit_interactions_event_id UNIQUE (event_id),
        CONSTRAINT ck_benefit_interactions_event_type CHECK (event_type IN (N'open', N'rejection', N'acceptance', N'click', N'dismissal', N'conversion')),
        CONSTRAINT ck_benefit_interactions_reward CHECK (reward IN (0.00, 0.20, 1.00))
    );
END;
GO

IF OBJECT_ID(N'ecloe_pay.loan_requests', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.loan_requests (
        loan_request_id NVARCHAR(80) NOT NULL CONSTRAINT pk_loan_requests PRIMARY KEY,
        user_id NVARCHAR(64) NOT NULL,
        requested_amount_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_loan_requests_currency DEFAULT 'BRL',
        status NVARCHAR(24) NOT NULL,
        requested_at DATETIMEOFFSET(7) NOT NULL,
        synthetic_notice NVARCHAR(240) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_loan_requests_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_loan_requests_demo_users
            FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
        CONSTRAINT ck_loan_requests_amount CHECK (requested_amount_cents > 0),
        CONSTRAINT ck_loan_requests_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_loan_requests_status CHECK (status IN (N'requested', N'under_review', N'cancelled'))
    );
END;
GO

IF OBJECT_ID(N'ecloe_pay.object_buckets', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.object_buckets (
        bucket_name NVARCHAR(80) NOT NULL CONSTRAINT pk_object_buckets PRIMARY KEY,
        purpose NVARCHAR(400) NOT NULL,
        pii_allowed BIT NOT NULL CONSTRAINT df_object_buckets_pii_allowed DEFAULT 0,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_object_buckets_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT ck_object_buckets_pii_allowed CHECK (pii_allowed = 0)
    );
END;
GO

IF OBJECT_ID(N'ecloe_pay.outbox_events', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.outbox_events (
        outbox_event_id NVARCHAR(80) NOT NULL CONSTRAINT pk_outbox_events PRIMARY KEY,
        event_id NVARCHAR(80) NOT NULL,
        aggregate_type NVARCHAR(80) NOT NULL,
        aggregate_id NVARCHAR(80) NOT NULL,
        event_type NVARCHAR(80) NOT NULL,
        payload NVARCHAR(MAX) NOT NULL,
        occurred_at DATETIMEOFFSET(7) NOT NULL,
        published_at DATETIMEOFFSET(7) NULL,
        attempts INT NOT NULL CONSTRAINT df_outbox_events_attempts DEFAULT 0,
        CONSTRAINT uq_outbox_events_event_id UNIQUE (event_id),
        CONSTRAINT ck_outbox_events_payload_json CHECK (ISJSON(payload) = 1),
        CONSTRAINT ck_outbox_events_attempts CHECK (attempts >= 0),
        CONSTRAINT ck_outbox_events_event_type CHECK (event_type IN (N'open', N'rejection', N'acceptance', N'click', N'dismissal', N'conversion', N'payment_verified', N'payment_rejected'))
    );
END;
GO

IF OBJECT_ID(N'ecloe_pay.schema_migrations', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.schema_migrations (
        migration_id NVARCHAR(120) NOT NULL CONSTRAINT pk_schema_migrations PRIMARY KEY,
        applied_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_schema_migrations_applied_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00'))
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM ecloe_pay.object_buckets WHERE bucket_name = N'ecloe-pay-demo-artifacts'
)
BEGIN
    INSERT INTO ecloe_pay.object_buckets (bucket_name, purpose, pii_allowed)
    VALUES (
        N'ecloe-pay-demo-artifacts',
        N'ECloe Pay simulated receipt exports, screenshots, and demo evidence without personal or payment credentials',
        0
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM ecloe_pay.schema_migrations WHERE migration_id = N'20260728_ecloe_pay_azure_sql_schema'
)
BEGIN
    INSERT INTO ecloe_pay.schema_migrations (migration_id)
    VALUES (N'20260728_ecloe_pay_azure_sql_schema');
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM ecloe_pay.schema_migrations
    WHERE migration_id = N'20260811_ecloe_pay_recommendation_events_v2'
)
BEGIN
    IF OBJECT_ID(N'ecloe_pay.ck_benefit_interactions_event_type', N'C') IS NOT NULL
        ALTER TABLE ecloe_pay.benefit_interactions DROP CONSTRAINT ck_benefit_interactions_event_type;
    ALTER TABLE ecloe_pay.benefit_interactions WITH CHECK ADD CONSTRAINT ck_benefit_interactions_event_type
        CHECK (event_type IN (N'open', N'rejection', N'acceptance', N'click', N'dismissal', N'conversion'));

    IF OBJECT_ID(N'ecloe_pay.ck_outbox_events_event_type', N'C') IS NOT NULL
        ALTER TABLE ecloe_pay.outbox_events DROP CONSTRAINT ck_outbox_events_event_type;
    ALTER TABLE ecloe_pay.outbox_events WITH CHECK ADD CONSTRAINT ck_outbox_events_event_type
        CHECK (event_type IN (N'open', N'rejection', N'acceptance', N'click', N'dismissal', N'conversion', N'payment_verified', N'payment_rejected'));

    INSERT INTO ecloe_pay.schema_migrations (migration_id)
    VALUES (N'20260811_ecloe_pay_recommendation_events_v2');
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM ecloe_pay.schema_migrations
    WHERE migration_id = N'20260812_ecloe_external_identity_v1'
)
BEGIN
    IF COL_LENGTH(N'ecloe_pay.demo_users', N'auth_provider') IS NULL
        ALTER TABLE ecloe_pay.demo_users ADD auth_provider NVARCHAR(40) NOT NULL
            CONSTRAINT df_demo_users_auth_provider DEFAULT N'local';
    IF COL_LENGTH(N'ecloe_pay.demo_users', N'provisioning_version') IS NULL
        ALTER TABLE ecloe_pay.demo_users ADD provisioning_version INT NOT NULL
            CONSTRAINT df_demo_users_provisioning_version DEFAULT 1;
    ALTER TABLE ecloe_pay.demo_users ALTER COLUMN password_hash NVARCHAR(512) NULL;

    IF COL_LENGTH(N'ecloe_pay.auth_sessions', N'idle_expires_at') IS NULL
    BEGIN
        ALTER TABLE ecloe_pay.auth_sessions ADD idle_expires_at DATETIMEOFFSET(7) NULL;
        UPDATE ecloe_pay.auth_sessions SET idle_expires_at = expires_at WHERE idle_expires_at IS NULL;
        ALTER TABLE ecloe_pay.auth_sessions ALTER COLUMN idle_expires_at DATETIMEOFFSET(7) NOT NULL;
    END;

    IF OBJECT_ID(N'ecloe_pay.external_identities', N'U') IS NULL
    BEGIN
        CREATE TABLE ecloe_pay.external_identities (
            identity_id NVARCHAR(64) NOT NULL CONSTRAINT pk_external_identities PRIMARY KEY,
            user_id NVARCHAR(64) NOT NULL,
            provider NVARCHAR(40) NOT NULL,
            issuer NVARCHAR(300) NOT NULL,
            subject_key CHAR(64) NOT NULL,
            created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_external_identities_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
            last_login_at DATETIMEOFFSET(7) NULL,
            CONSTRAINT fk_external_identities_user FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
            CONSTRAINT uq_external_identities_subject UNIQUE (provider, issuer, subject_key)
        );
    END;

    IF OBJECT_ID(N'ecloe_pay.oidc_login_flows', N'U') IS NULL
    BEGIN
        CREATE TABLE ecloe_pay.oidc_login_flows (
            flow_id NVARCHAR(64) NOT NULL CONSTRAINT pk_oidc_login_flows PRIMARY KEY,
            token_hash CHAR(64) NOT NULL CONSTRAINT uq_oidc_login_flows_token UNIQUE,
            flow_payload NVARCHAR(MAX) NOT NULL,
            return_to NVARCHAR(500) NOT NULL,
            intent NVARCHAR(20) NOT NULL CONSTRAINT df_oidc_login_flows_intent DEFAULT N'login',
            created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_oidc_login_flows_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
            expires_at DATETIMEOFFSET(7) NOT NULL,
            CONSTRAINT ck_oidc_login_flows_intent CHECK (intent IN (N'login', N'signup')),
            CONSTRAINT ck_oidc_login_flows_payload CHECK (ISJSON(flow_payload) = 1)
        );
    END;

    IF OBJECT_ID(N'ecloe_pay.wallet_accounts', N'U') IS NULL
    BEGIN
        CREATE TABLE ecloe_pay.wallet_accounts (
            wallet_account_id NVARCHAR(64) NOT NULL CONSTRAINT pk_wallet_accounts PRIMARY KEY,
            user_id NVARCHAR(64) NOT NULL CONSTRAINT uq_wallet_accounts_user UNIQUE,
            available_balance_cents INT NOT NULL,
            cashback_cents INT NOT NULL,
            savings_goal_percent INT NOT NULL,
            currency CHAR(3) NOT NULL CONSTRAINT df_wallet_accounts_currency DEFAULT 'BRL',
            status NVARCHAR(40) NOT NULL CONSTRAINT df_wallet_accounts_status DEFAULT N'active',
            updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_wallet_accounts_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
            CONSTRAINT fk_wallet_accounts_user FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
            CONSTRAINT ck_wallet_accounts_balance CHECK (available_balance_cents >= 0),
            CONSTRAINT ck_wallet_accounts_cashback CHECK (cashback_cents >= 0),
            CONSTRAINT ck_wallet_accounts_goal CHECK (savings_goal_percent BETWEEN 0 AND 100),
            CONSTRAINT ck_wallet_accounts_currency CHECK (currency = 'BRL'),
            CONSTRAINT ck_wallet_accounts_status CHECK (status IN (N'active', N'review', N'inactive'))
        );
    END;

    IF OBJECT_ID(N'ecloe_pay.wallet_transactions', N'U') IS NULL
    BEGIN
        CREATE TABLE ecloe_pay.wallet_transactions (
            user_id NVARCHAR(64) NOT NULL,
            transaction_id NVARCHAR(64) NOT NULL,
            description NVARCHAR(180) NOT NULL,
            amount_cents INT NOT NULL,
            category NVARCHAR(60) NOT NULL,
            occurred_at DATETIMEOFFSET(7) NOT NULL,
            CONSTRAINT pk_wallet_transactions PRIMARY KEY (user_id, transaction_id),
            CONSTRAINT fk_wallet_transactions_user FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id)
        );
    END;

IF OBJECT_ID(N'ecloe_pay.consent_acceptances', N'U') IS NULL
BEGIN
        CREATE TABLE ecloe_pay.consent_acceptances (
            acceptance_id NVARCHAR(64) NOT NULL CONSTRAINT pk_consent_acceptances PRIMARY KEY,
            user_id NVARCHAR(64) NOT NULL,
            document_type NVARCHAR(40) NOT NULL,
            document_version NVARCHAR(40) NOT NULL,
            accepted_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_consent_acceptances_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
            CONSTRAINT fk_consent_acceptances_user FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
            CONSTRAINT uq_consent_acceptances UNIQUE (user_id, document_type, document_version)
        );
    END;

    IF OBJECT_ID(N'ecloe_pay.security_audit_events', N'U') IS NULL
    BEGIN
        CREATE TABLE ecloe_pay.security_audit_events (
            audit_event_id NVARCHAR(64) NOT NULL CONSTRAINT pk_security_audit_events PRIMARY KEY,
            user_id NVARCHAR(64) NULL,
            event_type NVARCHAR(60) NOT NULL,
            result NVARCHAR(40) NOT NULL,
            occurred_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_security_audit_events_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
            CONSTRAINT fk_security_audit_events_user FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id)
        );
    END;

    INSERT INTO ecloe_pay.schema_migrations (migration_id)
    VALUES (N'20260812_ecloe_external_identity_v1');
END;
GO

IF COL_LENGTH(N'ecloe_pay.oidc_login_flows', N'intent') IS NULL
BEGIN
    ALTER TABLE ecloe_pay.oidc_login_flows
        ADD intent NVARCHAR(20) NOT NULL
            CONSTRAINT df_oidc_login_flows_intent DEFAULT N'login';
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'ck_oidc_login_flows_intent'
        AND parent_object_id = OBJECT_ID(N'ecloe_pay.oidc_login_flows')
)
BEGIN
    ALTER TABLE ecloe_pay.oidc_login_flows
        ADD CONSTRAINT ck_oidc_login_flows_intent CHECK (intent IN (N'login', N'signup'));
END;
GO

IF OBJECT_ID(N'ecloe_pay.signup_registrations', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.signup_registrations (
        registration_id NVARCHAR(64) NOT NULL CONSTRAINT pk_signup_registrations PRIMARY KEY,
        ip_hash CHAR(64) NOT NULL,
        user_id NVARCHAR(64) NULL,
        provider NVARCHAR(40) NOT NULL,
        issuer NVARCHAR(300) NOT NULL,
        subject_key CHAR(64) NOT NULL,
        result NVARCHAR(40) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_signup_registrations_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_signup_registrations_user FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
        CONSTRAINT ck_signup_registrations_result CHECK (result IN (N'success', N'blocked_ip_limit'))
    );
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'ux_signup_registrations_success_ip'
        AND object_id = OBJECT_ID(N'ecloe_pay.signup_registrations')
)
BEGIN
    DROP INDEX ux_signup_registrations_success_ip
        ON ecloe_pay.signup_registrations;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'ix_signup_registrations_success_ip'
        AND object_id = OBJECT_ID(N'ecloe_pay.signup_registrations')
)
BEGIN
    CREATE INDEX ix_signup_registrations_success_ip
        ON ecloe_pay.signup_registrations (ip_hash)
        WHERE result = N'success';
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'ix_signup_registrations_subject'
        AND object_id = OBJECT_ID(N'ecloe_pay.signup_registrations')
)
BEGIN
    CREATE INDEX ix_signup_registrations_subject
        ON ecloe_pay.signup_registrations (provider, issuer, subject_key);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_auth_sessions_valid' AND object_id = OBJECT_ID(N'ecloe_pay.auth_sessions')
)
BEGIN
    CREATE INDEX ix_auth_sessions_valid
        ON ecloe_pay.auth_sessions (user_id, expires_at)
        WHERE revoked_at IS NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_demo_sessions_user' AND object_id = OBJECT_ID(N'ecloe_pay.demo_sessions')
)
BEGIN
    CREATE INDEX ix_demo_sessions_user
        ON ecloe_pay.demo_sessions (user_id, created_at DESC);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_demo_user_profiles_country' AND object_id = OBJECT_ID(N'ecloe_pay.demo_user_profiles')
)
BEGIN
    CREATE INDEX ix_demo_user_profiles_country
        ON ecloe_pay.demo_user_profiles (country, state_region, city);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_payment_orders_session' AND object_id = OBJECT_ID(N'ecloe_pay.payment_orders')
)
BEGIN
    CREATE INDEX ix_payment_orders_session
        ON ecloe_pay.payment_orders (session_id, created_at DESC);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_benefit_interactions_session' AND object_id = OBJECT_ID(N'ecloe_pay.benefit_interactions')
)
BEGIN
    CREATE INDEX ix_benefit_interactions_session
        ON ecloe_pay.benefit_interactions (session_id, occurred_at DESC);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_loan_requests_user' AND object_id = OBJECT_ID(N'ecloe_pay.loan_requests')
)
BEGIN
    CREATE INDEX ix_loan_requests_user
        ON ecloe_pay.loan_requests (user_id, requested_at DESC);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_outbox_events_unpublished' AND object_id = OBJECT_ID(N'ecloe_pay.outbox_events')
)
BEGIN
    CREATE INDEX ix_outbox_events_unpublished
        ON ecloe_pay.outbox_events (occurred_at)
        WHERE published_at IS NULL;
END;
GO

IF OBJECT_ID(N'ecloe_pay.wallet_payment_transactions', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.wallet_payment_transactions (
        payment_id NVARCHAR(80) NOT NULL CONSTRAINT pk_wallet_payment_transactions PRIMARY KEY,
        idempotency_key NVARCHAR(180) NOT NULL CONSTRAINT uq_wallet_payment_transactions_idempotency UNIQUE,
        user_id NVARCHAR(64) NOT NULL,
        market_order_id NVARCHAR(80) NOT NULL,
        amount_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_wallet_payment_transactions_currency DEFAULT 'BRL',
        status NVARCHAR(24) NOT NULL,
        balance_after_cents INT NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_wallet_payment_transactions_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_wallet_payment_transactions_user FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
        CONSTRAINT ck_wallet_payment_transactions_amount CHECK (amount_cents > 0),
        CONSTRAINT ck_wallet_payment_transactions_balance CHECK (balance_after_cents >= 0),
        CONSTRAINT ck_wallet_payment_transactions_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_wallet_payment_transactions_status CHECK (status IN (N'paid', N'refunded'))
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM ecloe_pay.schema_migrations
    WHERE migration_id = N'20260813_ecloe_pay_wallet_market_payments_v1'
)
BEGIN
    INSERT INTO ecloe_pay.schema_migrations (migration_id)
    VALUES (N'20260813_ecloe_pay_wallet_market_payments_v1');
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM ecloe_pay.schema_migrations
    WHERE migration_id = N'20260814_ecloe_pay_loan_requests_v1'
)
BEGIN
    INSERT INTO ecloe_pay.schema_migrations (migration_id)
    VALUES (N'20260814_ecloe_pay_loan_requests_v1');
END;
GO
