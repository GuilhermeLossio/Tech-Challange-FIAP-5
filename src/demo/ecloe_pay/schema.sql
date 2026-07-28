IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ecloe_pay')
BEGIN
    EXEC(N'CREATE SCHEMA ecloe_pay');
END;

IF OBJECT_ID(N'ecloe_pay.demo_users', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.demo_users (
        user_id NVARCHAR(64) NOT NULL CONSTRAINT pk_demo_users PRIMARY KEY,
        email NVARCHAR(254) NOT NULL,
        password_hash NVARCHAR(512) NOT NULL,
        display_name NVARCHAR(120) NOT NULL,
        persona_label NVARCHAR(120) NOT NULL,
        pii_allowed BIT NOT NULL CONSTRAINT df_demo_users_pii_allowed DEFAULT 0,
        created_at DATETIME2(3) NOT NULL CONSTRAINT df_demo_users_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT uq_demo_users_email UNIQUE (email),
        CONSTRAINT ck_demo_users_pii_allowed CHECK (pii_allowed = 0)
    );
END;

IF OBJECT_ID(N'ecloe_pay.auth_sessions', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.auth_sessions (
        auth_session_id NVARCHAR(64) NOT NULL CONSTRAINT pk_auth_sessions PRIMARY KEY,
        user_id NVARCHAR(64) NOT NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT df_auth_sessions_created_at DEFAULT SYSUTCDATETIME(),
        expires_at DATETIME2(3) NOT NULL,
        revoked_at DATETIME2(3) NULL,
        CONSTRAINT fk_auth_sessions_demo_users
            FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id)
    );
END;

IF OBJECT_ID(N'ecloe_pay.demo_sessions', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.demo_sessions (
        session_id NVARCHAR(64) NOT NULL CONSTRAINT pk_demo_sessions PRIMARY KEY,
        user_id NVARCHAR(64) NOT NULL,
        demo_subject_key NVARCHAR(120) NOT NULL,
        selected_decision_id NVARCHAR(80) NULL,
        selected_offer_id NVARCHAR(80) NULL,
        terms_accepted BIT NOT NULL CONSTRAINT df_demo_sessions_terms_accepted DEFAULT 0,
        created_at DATETIME2(3) NOT NULL CONSTRAINT df_demo_sessions_created_at DEFAULT SYSUTCDATETIME(),
        expires_at DATETIME2(3) NOT NULL,
        locked_at DATETIME2(3) NULL,
        CONSTRAINT fk_demo_sessions_demo_users
            FOREIGN KEY (user_id) REFERENCES ecloe_pay.demo_users(user_id),
        CONSTRAINT ck_demo_sessions_session_id CHECK (session_id LIKE N'sess_%')
    );
END;

IF OBJECT_ID(N'ecloe_pay.wallet_snapshots', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.wallet_snapshots (
        snapshot_id NVARCHAR(64) NOT NULL CONSTRAINT pk_wallet_snapshots PRIMARY KEY,
        session_id NVARCHAR(64) NOT NULL,
        demo_balance_cents INT NOT NULL,
        cashback_cents INT NOT NULL,
        savings_goal_percent INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_wallet_snapshots_currency DEFAULT 'BRL',
        created_at DATETIME2(3) NOT NULL CONSTRAINT df_wallet_snapshots_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT fk_wallet_snapshots_demo_sessions
            FOREIGN KEY (session_id) REFERENCES ecloe_pay.demo_sessions(session_id),
        CONSTRAINT ck_wallet_snapshots_demo_balance CHECK (demo_balance_cents >= 0),
        CONSTRAINT ck_wallet_snapshots_cashback CHECK (cashback_cents >= 0),
        CONSTRAINT ck_wallet_snapshots_savings_goal CHECK (savings_goal_percent BETWEEN 0 AND 100)
    );
END;

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
        created_at DATETIME2(3) NOT NULL CONSTRAINT df_payment_orders_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(3) NOT NULL CONSTRAINT df_payment_orders_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT fk_payment_orders_demo_sessions
            FOREIGN KEY (session_id) REFERENCES ecloe_pay.demo_sessions(session_id),
        CONSTRAINT uq_payment_orders_idempotency_key UNIQUE (idempotency_key),
        CONSTRAINT ck_payment_orders_amount CHECK (amount_cents > 0),
        CONSTRAINT ck_payment_orders_status CHECK (status IN (N'created', N'verified', N'rejected', N'cancelled'))
    );
END;

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
        occurred_at DATETIME2(3) NOT NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT df_benefit_interactions_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT fk_benefit_interactions_demo_sessions
            FOREIGN KEY (session_id) REFERENCES ecloe_pay.demo_sessions(session_id),
        CONSTRAINT uq_benefit_interactions_event_id UNIQUE (event_id),
        CONSTRAINT ck_benefit_interactions_event_type CHECK (event_type IN (N'click', N'dismissal', N'conversion')),
        CONSTRAINT ck_benefit_interactions_reward CHECK (reward IN (0.00, 0.20, 1.00))
    );
END;

IF OBJECT_ID(N'ecloe_pay.object_buckets', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.object_buckets (
        bucket_name NVARCHAR(80) NOT NULL CONSTRAINT pk_object_buckets PRIMARY KEY,
        purpose NVARCHAR(400) NOT NULL,
        pii_allowed BIT NOT NULL CONSTRAINT df_object_buckets_pii_allowed DEFAULT 0,
        created_at DATETIME2(3) NOT NULL CONSTRAINT df_object_buckets_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT ck_object_buckets_pii_allowed CHECK (pii_allowed = 0)
    );
END;

IF OBJECT_ID(N'ecloe_pay.outbox_events', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_pay.outbox_events (
        outbox_event_id NVARCHAR(80) NOT NULL CONSTRAINT pk_outbox_events PRIMARY KEY,
        aggregate_type NVARCHAR(80) NOT NULL,
        aggregate_id NVARCHAR(80) NOT NULL,
        event_type NVARCHAR(80) NOT NULL,
        payload NVARCHAR(MAX) NOT NULL,
        occurred_at DATETIME2(3) NOT NULL,
        published_at DATETIME2(3) NULL,
        attempts INT NOT NULL CONSTRAINT df_outbox_events_attempts DEFAULT 0,
        CONSTRAINT ck_outbox_events_payload_json CHECK (ISJSON(payload) = 1),
        CONSTRAINT ck_outbox_events_attempts CHECK (attempts >= 0)
    );
END;

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
