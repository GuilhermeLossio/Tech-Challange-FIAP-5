import json
from pathlib import Path
from typing import get_type_hints

ROOT = Path(__file__).resolve().parents[1]
PAY_DEMO = ROOT / "src" / "demo" / "ecloe_pay"


def i18n_messages(locale: str) -> dict:
    return json.loads((PAY_DEMO / "i18n" / f"{locale}.json").read_text(encoding="utf-8"))


def flatten_keys(data: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys.update(flatten_keys(value, full_key))
        else:
            keys.add(full_key)
    return keys


def test_pay_i18n_catalogs_have_matching_required_keys() -> None:
    assert flatten_keys(i18n_messages("pt-BR")) == flatten_keys(i18n_messages("en-US"))


def test_pay_demo_declares_simulation_boundaries() -> None:
    html = (PAY_DEMO / "index.html").read_text(encoding="utf-8")
    pt = i18n_messages("pt-BR")
    en = i18n_messages("en-US")

    assert 't("wallet.termsCopy1")' in html
    assert 't("wallet.termsCopy2")' in html
    assert 't("wallet.noRealValue")' in html
    assert "nao cria usuarios reais" in pt["wallet"]["termsCopy1"]
    assert "no real money is processed" in en["wallet"]["termsCheck"]
    assert "No real value is stored or moved" in en["wallet"]["noRealValue"]


def test_pay_wallet_markup_uses_accessible_semantics() -> None:
    html = (PAY_DEMO / "index.html").read_text(encoding="utf-8")
    core_styles = (PAY_DEMO / "core.css").read_text(encoding="utf-8")
    wallet_styles = (PAY_DEMO / "wallet.css").read_text(encoding="utf-8")

    assert 'lang="{{ lang }}"' in html
    assert 'href="./wallet.css"' in html
    assert 'aria-label="{{ t("wallet.navAria") }}"' in html
    assert '<nav class="quick-actions" aria-label="{{ t("wallet.quickActionsAria") }}">' in html
    assert 'class="nav-link active"' in html
    assert 'role="progressbar"' in html
    assert 'aria-valuenow="0"' in html
    assert 'id="balanceAmount">--</strong>' in html
    assert 'id="cashbackAmount">--</strong>' in html
    assert 'id="paymentAmount">--</strong>' in html
    assert 'id="loanAmount">--</strong>' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'formmethod="dialog">{{ t("wallet.cancel") }}' in html
    assert '<article class="companion-card"' not in html
    assert '<footer class="status-panel' not in html
    assert ".companion-heading" in wallet_styles
    assert ".nav-link.active" in wallet_styles
    assert ".sr-only" in core_styles


def test_pay_demo_has_dedicated_azure_sql_schema_and_bucket() -> None:
    schema = (PAY_DEMO / "schema.sql").read_text(encoding="utf-8")
    schema_lower = schema.lower()

    assert "CREATE SCHEMA ecloe_pay" in schema
    assert "ecloe_pay.payment_orders" in schema
    assert "ecloe_pay.loan_requests" in schema
    assert "ecloe_pay.benefit_interactions" in schema
    assert "ecloe_pay.demo_users" in schema
    assert "ecloe_pay.demo_user_profiles" in schema
    assert "ecloe_pay.auth_sessions" in schema
    assert "ecloe_pay.demo_sessions" in schema
    assert "ecloe_pay.wallet_snapshots" in schema
    assert "ecloe-pay-demo-artifacts" in schema
    assert "ecloe_pay.schema_migrations" in schema
    assert "email_normalized NVARCHAR(254) MASKED WITH (FUNCTION = 'email()') NOT NULL" in schema
    assert "full_name NVARCHAR(160) MASKED WITH" in schema
    assert "address_line1 NVARCHAR(240) MASKED WITH" in schema
    assert "postal_code NVARCHAR(40) MASKED WITH" in schema
    assert "phone NVARCHAR(40) MASKED WITH" in schema
    assert "sys.masked_columns" in schema
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
    assert "ix_demo_user_profiles_country" in schema
    assert "ix_demo_sessions_user" in schema
    assert "ix_payment_orders_session" in schema
    assert "ix_loan_requests_user" in schema
    assert "ix_benefit_interactions_session" in schema
    assert "ix_outbox_events_unpublished" in schema
    assert "ix_signup_registrations_success_ip" in schema
    assert "CREATE UNIQUE INDEX ux_signup_registrations_success_ip" not in schema
    assert "TIMESTAMPTZ" not in schema
    assert "JSONB" not in schema
    assert "ON CONFLICT" not in schema
    assert "CREATE TABLE IF NOT EXISTS" not in schema
    assert "DATETIME2" not in schema
    assert "now()" not in schema_lower
    assert "ck_loan_requests_status CHECK (status IN (N'requested', N'under_review', N'cancelled'))" in schema
    assert "loan_requests_status CHECK (status IN (N'approved" not in schema_lower
    for forbidden_column in [
        "cpf",
        "document_number",
        "card_number",
        "cardholder",
        "cvv",
        "bank_account",
        "agency",
        "routing_number",
        "account_number",
        "credit_score",
        "income",
        "wealth",
    ]:
        assert forbidden_column not in schema_lower


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
        "loan_requests",
        "simulate_payment",
        "reset_demo_state",
        "health_check",
    }

    assert "sqlalchemy" not in app_source.lower()
    assert contract <= set(PayRepository.__dict__)
    assert contract <= set(MemoryPayRepository.__dict__)
    assert contract <= set(AzureSqlPayRepository.__dict__)
    assert get_type_hints(PayRepository.create_auth_session)


def test_pay_authentication_uses_secure_cookie_csrf_and_rate_limit() -> None:
    app_source = (PAY_DEMO / "app.py").read_text(encoding="utf-8")
    script = (PAY_DEMO / "app.js").read_text(encoding="utf-8")
    login_script = (PAY_DEMO / "login.js").read_text(encoding="utf-8")
    login = (PAY_DEMO / "login.html").read_text(encoding="utf-8")
    azure_source = (PAY_DEMO / "repositories" / "azure_sql.py").read_text(encoding="utf-8")

    assert "AUTH_COOKIE_NAME = \"ecloe_pay_session\"" in app_source
    assert "CSRF_COOKIE_NAME = \"ecloe_pay_csrf\"" in app_source
    assert "httponly=True" in app_source
    assert "secure=_cookie_secure(settings)" in app_source
    assert "samesite=\"Lax\"" in app_source
    assert "path=\"/\"" in app_source
    assert "max_age=settings.ecloe_pay_session_ttl_seconds" in app_source
    assert "settings.app_environment != \"local\"" in app_source
    assert "hmac.compare_digest" in app_source
    assert "request.cookies.get(CSRF_COOKIE_NAME) or secrets.token_urlsafe" not in app_source
    assert "LOGIN_RATE_LIMIT_ATTEMPTS" in app_source
    assert "Cache-Control" in app_source
    assert "redirect(_localized_login_url(locale))" in app_source
    assert "make_response" in app_source
    assert "session[" not in app_source
    assert "X-CSRF-Token" in script
    assert "X-CSRF-Token" in login_script
    assert 'src="../login.js"' in login
    assert "token_hash(raw_token)" in azure_source
    logger_lines = [line.lower() for line in app_source.splitlines() if "LOGGER.info" in line]
    assert logger_lines
    assert all("password" not in line and "email" not in line for line in logger_lines)


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
    index = (PAY_DEMO / "index.html").read_text(encoding="utf-8")

    assert "transactionLocked" in script
    assert "Previa duplicada ignorada" in script
    assert "confirmationCode" in script
    assert "pre-visualizado" in script
    assert "localStorage" not in script
    assert "/api/auth/me" in script
    assert "/api/auth/logout" in script
    assert "postgres_schema" not in script
    assert "sql_schema" not in script
    assert "database_provider" in script
    assert "database_schema" in script
    assert "Modo apresentacao" in script
    assert "formatMoney" in script
    assert "renderSession(body)" in script
    for fixed_value in ("R$ 428,70", "R$ 18,40", "64%", "R$ 127,90"):
        assert fixed_value not in index
    assert 't("wallet.presentationMode")' in index
    assert "postgres_schema" not in index
    assert "PostgreSQL" not in index


def test_pay_login_page_matches_demo_identity_and_csrf_flow() -> None:
    login = (PAY_DEMO / "login.html").read_text(encoding="utf-8")
    core_styles = (PAY_DEMO / "core.css").read_text(encoding="utf-8")
    login_styles = (PAY_DEMO / "login.css").read_text(encoding="utf-8")
    login_script = (PAY_DEMO / "login.js").read_text(encoding="utf-8")
    pt = i18n_messages("pt-BR")

    assert 't("login.badge")' in login
    assert 't("login.eyebrow")' in login
    assert pt["login"]["badge"] == "Identidade demonstrativa - nenhuma conta bancaria real"
    assert pt["login"]["eyebrow"] == "Carteira 100% simulada"
    assert "Azure SQL" in pt["login"]["copy"]
    assert 'href="../login.css"' in login
    assert "X-CSRF-Token" in login_script
    assert 'id="loginForm"' in login
    assert 'id="email"' in login
    assert 'id="password"' in login
    assert "demo.market@ecloe.local" not in login
    assert 'value="demo.pay@ecloe.local"' not in login
    assert "demo.pay@ecloe.local" not in login
    assert "change-this-demo-password" not in login
    assert "Configured demo password" not in login
    assert "localStorage" not in login
    assert "PostgreSQL" not in login
    assert "Baloo+2" in core_styles
    assert "Nunito" in core_styles
    assert "Space+Mono" in core_styles
    assert "--color-rose-soft: #ffe1ec" in core_styles
    assert "--color-mint-soft: #e3fbf3" in core_styles
    assert ".login-eyebrow" in login_styles
    assert ".login-safety-list" in login_styles


def test_pay_demo_css_is_split_by_page_and_uses_shared_utilities() -> None:
    index = (PAY_DEMO / "index.html").read_text(encoding="utf-8")
    landing = (PAY_DEMO / "landing.html").read_text(encoding="utf-8")
    login = (PAY_DEMO / "login.html").read_text(encoding="utf-8")
    aggregate = (PAY_DEMO / "styles.css").read_text(encoding="utf-8")
    core_styles = (PAY_DEMO / "core.css").read_text(encoding="utf-8")
    wallet_styles = (PAY_DEMO / "wallet.css").read_text(encoding="utf-8")

    assert 'href="./wallet.css"' in index
    assert 'href="./landing.css"' in landing
    assert 'href="../login.css"' in login
    assert '@import url("./core.css");' in aggregate
    assert ".card" in core_styles
    assert "--font-display" in core_styles
    assert "--font-mono" in core_styles
    assert "[aria-current" not in wallet_styles


def test_pay_demo_documents_flask_run_command() -> None:
    readme = (PAY_DEMO / "README.md").read_text(encoding="utf-8")

    assert 'python.exe -m flask --app "src.demo.ecloe_pay.app:create_server_app" run' in readme
    assert "http://127.0.0.1:5000/" in readme
    assert ".\\scripts\\allow_current_sql_client_ip.ps1" in readme
    assert ".\\scripts\\remove_current_sql_client_ip.ps1" in readme


def test_cloud_notebook_documents_pay_login_xlsx_seed_and_masking() -> None:
    notebook = (ROOT / "notebooks" / "05_cloud_artifacts_and_cosmos.ipynb").read_text(encoding="utf-8")

    assert "ECloe Pay Azure SQL Login Seed" in notebook
    assert "scripts.seed_ecloe_pay_login_xlsx --generate" in notebook
    assert "data/demo/ecloe_pay_login_seed.local.xlsx" in notebook
    assert "data/demo/*.local.xlsx" in notebook
    assert "ecloe_pay.demo_user_profiles" in notebook
    assert "Azure SQL Dynamic Data Masking" in notebook
    assert "runtime_unmask_permission" in notebook
    assert "not granted" in notebook
    assert "plaintext passwords are never stored in SQL" in notebook


def test_pay_landing_declares_demo_storage_and_financial_boundaries() -> None:
    landing = (PAY_DEMO / "landing.html").read_text(encoding="utf-8").lower()
    en = i18n_messages("en-US")

    assert 't("landing.eyebrow")' in landing
    assert 'href="/pay/login?lang={{ locale }}"' in landing
    assert "without creating users or processing real money" in en["landing"]["lede"]
    assert "ecloe-pay-demo-artifacts" in landing
    assert "ecloe_pay" in landing
    assert "does not create real users" in en["landing"]["disclaimerCopy"]
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


def test_pay_sql_firewall_scripts_keep_local_ip_rule_narrow() -> None:
    allow_script = (ROOT / "scripts" / "allow_current_sql_client_ip.ps1").read_text(encoding="utf-8")
    remove_script = (ROOT / "scripts" / "remove_current_sql_client_ip.ps1").read_text(encoding="utf-8")
    legacy_script = (ROOT / "scripts" / "allow_ecloe_pay_sql_current_ip.ps1").read_text(encoding="utf-8")

    assert "AllowCurrentClientIp" in allow_script
    assert "ecloe-sql-1266" in allow_script
    assert "Type ENABLE" in allow_script
    assert "--enable-public-network" in allow_script
    assert '$ip -eq "0.0.0.0"' in allow_script
    assert "https://api.ipify.org?format=text" in allow_script
    assert "--start-ip-address" in allow_script
    assert "--end-ip-address" in allow_script
    assert ".\\scripts\\remove_current_sql_client_ip.ps1" in allow_script
    assert "firewall-rule" in remove_script
    assert "delete" in remove_script
    assert "allow_current_sql_client_ip.ps1" in legacy_script
