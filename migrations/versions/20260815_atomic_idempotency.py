"""Add persisted request fingerprints for atomic idempotency checks."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260815_atomic_idempotency"
down_revision: str | None = "20260728_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        IF COL_LENGTH(N'ecloe_pay.payment_orders', N'request_hash') IS NULL
        BEGIN
            ALTER TABLE ecloe_pay.payment_orders ADD request_hash CHAR(64) NOT NULL
                CONSTRAINT df_payment_orders_request_hash DEFAULT REPLICATE('0', 64);
        END;
        IF COL_LENGTH(N'ecloe_pay.wallet_payment_transactions', N'request_hash') IS NULL
        BEGIN
            ALTER TABLE ecloe_pay.wallet_payment_transactions ADD request_hash CHAR(64) NOT NULL
                CONSTRAINT df_wallet_payment_request_hash DEFAULT REPLICATE('0', 64);
        END;
        IF COL_LENGTH(N'ecloe_pay.benefit_interactions', N'request_hash') IS NULL
        BEGIN
            ALTER TABLE ecloe_pay.benefit_interactions ADD request_hash CHAR(64) NOT NULL
                CONSTRAINT df_benefit_interaction_request_hash DEFAULT REPLICATE('0', 64);
        END;
        IF COL_LENGTH(N'ecloe_market.checkout_sessions', N'request_hash') IS NULL
        BEGIN
            ALTER TABLE ecloe_market.checkout_sessions ADD request_hash CHAR(64) NOT NULL
                CONSTRAINT df_market_checkout_request_hash DEFAULT REPLICATE('0', 64);
        END;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        IF COL_LENGTH(N'ecloe_market.checkout_sessions', N'request_hash') IS NOT NULL
            ALTER TABLE ecloe_market.checkout_sessions DROP CONSTRAINT df_market_checkout_request_hash;
        IF COL_LENGTH(N'ecloe_market.checkout_sessions', N'request_hash') IS NOT NULL
            ALTER TABLE ecloe_market.checkout_sessions DROP COLUMN request_hash;
        IF COL_LENGTH(N'ecloe_pay.benefit_interactions', N'request_hash') IS NOT NULL
            ALTER TABLE ecloe_pay.benefit_interactions DROP CONSTRAINT df_benefit_interaction_request_hash;
        IF COL_LENGTH(N'ecloe_pay.benefit_interactions', N'request_hash') IS NOT NULL
            ALTER TABLE ecloe_pay.benefit_interactions DROP COLUMN request_hash;
        IF COL_LENGTH(N'ecloe_pay.wallet_payment_transactions', N'request_hash') IS NOT NULL
            ALTER TABLE ecloe_pay.wallet_payment_transactions DROP CONSTRAINT df_wallet_payment_request_hash;
        IF COL_LENGTH(N'ecloe_pay.wallet_payment_transactions', N'request_hash') IS NOT NULL
            ALTER TABLE ecloe_pay.wallet_payment_transactions DROP COLUMN request_hash;
        IF COL_LENGTH(N'ecloe_pay.payment_orders', N'request_hash') IS NOT NULL
            ALTER TABLE ecloe_pay.payment_orders DROP CONSTRAINT df_payment_orders_request_hash;
        IF COL_LENGTH(N'ecloe_pay.payment_orders', N'request_hash') IS NOT NULL
            ALTER TABLE ecloe_pay.payment_orders DROP COLUMN request_hash;
        """
    )
