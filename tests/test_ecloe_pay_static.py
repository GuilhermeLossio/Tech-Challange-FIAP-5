from pathlib import Path
from typing import get_type_hints

ROOT = Path(__file__).resolve().parents[1]
PAY_DEMO = ROOT / "src" / "demo" / "ecloe_pay"


def test_pay_demo_declares_simulation_boundaries() -> None:
    html = (PAY_DEMO / "index.html").read_text(encoding="utf-8")

    assert "does not create real users" in html
    assert "process real money" in html
    assert "Do not enter real card, bank, CPF, password, or account information" in html
    assert "No real funds are stored or moved" in html


def test_pay_demo_has_dedicated_azure_sql_schema_and_bucket() -> None:
    schema = (PAY_DEMO / "schema.sql").read_text(encoding="utf-8")

    assert "CREATE SCHEMA ecloe_pay" in schema
    assert "ecloe_pay.payment_orders" in schema
    assert "ecloe_pay.benefit_interactions" in schema
    assert "ecloe_pay.demo_users" in schema
    assert "ecloe_pay.auth_sessions" in schema
    assert "ecloe_pay.demo_sessions" in schema
    assert "ecloe_pay.wallet_snapshots" in schema
    assert "ecloe-pay-demo-artifacts" in schema
    assert "ecloe_pay.schema_migrations" in schema
    assert "email_normalized NVARCHAR(254) NOT NULL" in schema
    assert "token_hash NVARCHAR(128) NOT NULL" in schema
    assert "last_seen_at DATETIMEOFFSET(7) NULL" in schema
    assert "DATETIMEOFFSET(7)" in schema
    assert "CHECK (pii_allowed = 0)" in schema
    assert "CHECK (is_demo = 1)" in schema
    assert "CHECK (currency = 'BRL')" in schema
    assert "CHECK (ISJSON(payload) = 1)" in schema
    assert "uq_auth_sessions_token_hash" in schema
    assert "uq_payment_orders_idempotency_key" in schema
    assert "uq_outbox_events_event_id" in schema
    assert "ix_auth_sessions_valid" in schema
    assert "ix_outbox_events_unpublished" in schema
    assert "TIMESTAMPTZ" not in schema
    assert "JSONB" not in schema
    assert "ON CONFLICT" not in schema
    assert "CREATE TABLE IF NOT EXISTS" not in schema
    assert "DATETIME2" not in schema
    assert "now()" not in schema.lower()
    assert " cpf" not in schema.lower()
    assert " card" not in schema.lower()
    assert "bank_account" not in schema.lower()
    assert "agency" not in schema.lower()


def test_pay_repositories_expose_shared_contract_and_hide_sqlalchemy_from_routes() -> None:
    from src.demo.ecloe_pay.repositories.azure_sql import AzureSqlPayRepository
    from src.demo.ecloe_pay.repositories.base import PayRepository
    from src.demo.ecloe_pay.repositories.memory import MemoryPayRepository

    app_source = (PAY_DEMO / "app.py").read_text(encoding="utf-8")
    contract = {
        "get_user_by_email",
        "create_or_update_demo_user",
        "create_auth_session",
        "get_auth_session",
        "revoke_auth_session",
        "get_demo_session",
        "accept_terms",
        "record_benefit_interaction",
        "get_payment_order",
        "simulate_payment",
        "reset_demo_state",
        "health_check",
    }

    assert "sqlalchemy" not in app_source.lower()
    assert contract <= set(PayRepository.__dict__)
    assert contract <= set(MemoryPayRepository.__dict__)
    assert contract <= set(AzureSqlPayRepository.__dict__)
    assert get_type_hints(PayRepository.create_auth_session)


def test_pay_azure_sql_repository_uses_explicit_transactions_and_conditional_payment_update() -> None:
    source = (PAY_DEMO / "repositories" / "azure_sql.py").read_text(encoding="utf-8")

    assert "with self.engine.connect() as connection" in source
    assert "transaction = connection.begin()" in source
    assert "transaction.rollback()" in source
    assert "transaction.commit()" in source
    assert "WITH (UPDLOCK, ROWLOCK)" in source
    assert "AND status IN (N'created', N'rejected')" in source
    assert "result.rowcount != 1" in source
    assert "_record_benefit_interaction(connection" in source
    assert "_insert_outbox(" in source
    assert "if demo_session.payment_status == \"verified\"" not in source
    assert "with self.engine.begin()" not in source


def test_pay_demo_blocks_duplicate_simulated_payment() -> None:
    script = (PAY_DEMO / "app.js").read_text(encoding="utf-8")

    assert "transactionLocked" in script
    assert "Duplicate simulated payment blocked by idempotency" in script
    assert "confirmationCode" in script
    assert "POST /v1/rewards" in script
    assert "localStorage" not in script
    assert "/api/auth/me" in script
    assert "/api/auth/logout" in script
    assert "postgres_schema" not in script


def test_pay_demo_documents_flask_run_command() -> None:
    readme = (PAY_DEMO / "README.md").read_text(encoding="utf-8")

    assert "python.exe -m flask --app src.demo.ecloe_pay.app run" in readme
    assert "http://127.0.0.1:5000/" in readme


def test_pay_landing_declares_demo_storage_and_financial_boundaries() -> None:
    landing = (PAY_DEMO / "landing.html").read_text(encoding="utf-8").lower()

    assert "simulated payments demo" in landing
    assert "without creating users or processing real money" in landing
    assert "ecloe-pay-demo-artifacts" in landing
    assert "ecloe_pay" in landing
    assert "does not create real users" in landing
    assert "azure sql" in landing


def test_pay_bucket_script_documents_private_azure_container() -> None:
    script = (ROOT / "scripts" / "create_ecloe_pay_bucket.ps1").read_text(encoding="utf-8")
    cloud_doc = (ROOT / "docs" / "cloud-setup.md").read_text(encoding="utf-8")
    pay_doc = (ROOT / "docs" / "ecloe-pay.md").read_text(encoding="utf-8")
    readme = (PAY_DEMO / "README.md").read_text(encoding="utf-8")

    assert "ecloe-pay-demo-artifacts" in script
    assert "--public-access off" in script
    assert "--allow-blob-public-access false" in script
    assert "--min-tls-version TLS1_2" in script
    assert ".\\scripts\\create_ecloe_pay_bucket.ps1" in cloud_doc
    assert ".\\scripts\\create_ecloe_pay_bucket.ps1" in pay_doc
    assert ".\\scripts\\create_ecloe_pay_bucket.ps1" in readme
