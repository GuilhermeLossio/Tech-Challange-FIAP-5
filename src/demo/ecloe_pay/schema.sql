CREATE SCHEMA IF NOT EXISTS ecloe_pay;

CREATE TABLE IF NOT EXISTS ecloe_pay.demo_sessions (
    session_id TEXT PRIMARY KEY,
    demo_subject_key TEXT NOT NULL,
    selected_decision_id TEXT,
    selected_offer_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    locked_at TIMESTAMPTZ,
    CHECK (session_id LIKE 'sess_%')
);

CREATE TABLE IF NOT EXISTS ecloe_pay.wallet_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES ecloe_pay.demo_sessions(session_id),
    demo_balance_cents INTEGER NOT NULL CHECK (demo_balance_cents >= 0),
    cashback_cents INTEGER NOT NULL CHECK (cashback_cents >= 0),
    savings_goal_percent INTEGER NOT NULL CHECK (savings_goal_percent BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ecloe_pay.payment_orders (
    payment_order_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES ecloe_pay.demo_sessions(session_id),
    market_order_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency CHAR(3) NOT NULL DEFAULT 'BRL',
    status TEXT NOT NULL CHECK (status IN ('created', 'verified', 'rejected', 'cancelled')),
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ecloe_pay.benefit_interactions (
    interaction_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES ecloe_pay.demo_sessions(session_id),
    decision_id TEXT NOT NULL,
    offer_id TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL CHECK (event_type IN ('click', 'dismissal', 'conversion')),
    reward NUMERIC(4, 2) NOT NULL CHECK (reward IN (0.00, 0.20, 1.00)),
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ecloe_pay.object_buckets (
    bucket_name TEXT PRIMARY KEY,
    purpose TEXT NOT NULL,
    pii_allowed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (pii_allowed = false)
);

CREATE TABLE IF NOT EXISTS ecloe_pay.outbox_events (
    outbox_event_id TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0)
);

INSERT INTO ecloe_pay.object_buckets (bucket_name, purpose)
VALUES
    ('ecloe-pay-demo-artifacts', 'ECloe Pay simulated receipt exports, screenshots, and demo evidence without personal or payment credentials')
ON CONFLICT (bucket_name) DO NOTHING;
