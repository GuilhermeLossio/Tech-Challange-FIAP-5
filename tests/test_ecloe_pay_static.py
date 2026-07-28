from pathlib import Path

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
    assert "ecloe-pay-demo-artifacts" in schema
    assert "CHECK (pii_allowed = 0)" in schema
    assert "TIMESTAMPTZ" not in schema
    assert "JSONB" not in schema
    assert "ON CONFLICT" not in schema
    assert "CREATE TABLE IF NOT EXISTS" not in schema


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
