from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.core.config import load_settings
from src.demo.ecloe_pay.app import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, create_app
from src.demo.ecloe_pay.i18n import LOCALE_COOKIE_NAME
from src.demo.ecloe_pay.repositories import (
    DEMO_BUCKET_NAME,
    LEGACY_PAY_DEMO_USER_EMAIL,
    SHARED_DEMO_USER_EMAIL,
    MemoryPayRepository,
)


def local_signup_settings(**overrides):
    settings = replace(load_settings(use_env_file=False), ecloe_web_auth_mode="local_signup")
    return replace(settings, **overrides) if overrides else settings


def csrf_headers(client) -> dict[str, str]:
    cookie = client.get_cookie(CSRF_COOKIE_NAME)
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def authenticated_client(app=None):
    app = app or create_app()
    client = app.test_client()
    client.get("/pay/login")
    response = client.post(
        "/api/auth/login",
        json={"email": SHARED_DEMO_USER_EMAIL, "password": "change-this-demo-password"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200
    return client


def test_local_signup_login_page_exposes_register_link() -> None:
    app = create_app(settings=local_signup_settings())
    client = app.test_client()

    response = client.get("/pay/login?return_to=/pay&lang=pt-BR")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Criar conta" in body
    assert "/pay/register?return_to=/pay" in body


def test_local_mode_hides_register_link() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/pay/login?return_to=/pay&lang=pt-BR")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "/pay/register" not in body


def test_local_signup_register_creates_user_session_and_initial_balance() -> None:
    settings = local_signup_settings()
    repository = MemoryPayRepository(settings)
    app = create_app(settings=settings, repository=repository)
    client = app.test_client()
    client.get("/pay/register")

    response = client.post(
        "/api/auth/register",
        json={
            "email": "new.user@example.com",
            "password": "strong-pass",
            "password_confirm": "strong-pass",
        },
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["authenticated"] is True
    assert body["user"]["auth_provider"] == "local_signup"
    auth_cookie = client.get_cookie(AUTH_COOKIE_NAME)
    assert auth_cookie is not None and auth_cookie.http_only
    account = repository.synthetic_account(body["user"]["user_id"])
    assert account is not None
    assert account.available_balance_cents == 50000
    assert account.transactions[0].amount_cents == 50000
    persisted = repr(repository.users) + repr(repository.signup_registrations)
    assert "strong-pass" not in persisted


def test_local_signup_duplicate_email_returns_conflict() -> None:
    settings = local_signup_settings()
    repository = MemoryPayRepository(settings)
    app = create_app(settings=settings, repository=repository)
    first = app.test_client()
    first.get("/pay/register")
    payload = {
        "email": "duplicate@example.com",
        "password": "strong-pass",
        "password_confirm": "strong-pass",
    }
    assert first.post("/api/auth/register", json=payload, headers=csrf_headers(first)).status_code == 200
    second = app.test_client()
    second.get("/pay/register")

    response = second.post("/api/auth/register", json=payload, headers=csrf_headers(second))

    assert response.status_code == 409
    assert any(item["event_type"] == "signup_duplicate_email" for item in repository.audit_events)


def test_local_signup_blocks_second_new_user_from_same_ip_without_raw_ip_persistence() -> None:
    settings = local_signup_settings()
    repository = MemoryPayRepository(settings)
    app = create_app(settings=settings, repository=repository)
    first = app.test_client()
    first.get("/pay/register", headers={"X-Forwarded-For": "198.51.100.7"})
    assert first.post(
        "/api/auth/register",
        json={
            "email": "first@example.com",
            "password": "strong-pass",
            "password_confirm": "strong-pass",
        },
        headers={**csrf_headers(first), "X-Forwarded-For": "198.51.100.7"},
    ).status_code == 200
    second = app.test_client()
    second.get("/pay/register", headers={"X-Forwarded-For": "198.51.100.7"})

    response = second.post(
        "/api/auth/register",
        json={
            "email": "second@example.com",
            "password": "strong-pass",
            "password_confirm": "strong-pass",
        },
        headers={**csrf_headers(second), "X-Forwarded-For": "198.51.100.7"},
    )

    assert response.status_code == 403
    persisted = repr(repository.signup_registrations) + repr(repository.audit_events)
    assert "198.51.100.7" not in persisted
    assert "blocked_ip_limit" in persisted


def test_local_signup_allowlisted_ip_can_create_multiple_users() -> None:
    settings = local_signup_settings(ecloe_signup_admin_ip_allowlist=("198.51.100.7",))
    repository = MemoryPayRepository(settings)
    app = create_app(settings=settings, repository=repository)

    for email in ("first@example.com", "second@example.com"):
        client = app.test_client()
        client.get("/pay/register", headers={"X-Forwarded-For": "198.51.100.7"})
        response = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "strong-pass",
                "password_confirm": "strong-pass",
            },
            headers={**csrf_headers(client), "X-Forwarded-For": "198.51.100.7"},
        )
        assert response.status_code == 200

    registered = [
        item for item in repository.signup_registrations if item["provider"] == "local_signup"
    ]
    assert len(registered) == 2


def test_local_signup_users_get_distinct_demo_payment_orders() -> None:
    settings = local_signup_settings(ecloe_signup_admin_ip_allowlist=("198.51.100.7",))
    repository = MemoryPayRepository(settings)
    app = create_app(settings=settings, repository=repository)
    order_ids = []

    for email in ("first@example.com", "second@example.com"):
        client = app.test_client()
        client.get("/pay/register", headers={"X-Forwarded-For": "198.51.100.7"})
        response = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "strong-pass",
                "password_confirm": "strong-pass",
            },
            headers={**csrf_headers(client), "X-Forwarded-For": "198.51.100.7"},
        )
        assert response.status_code == 200
        user_id = response.get_json()["user"]["user_id"]
        order_ids.append(repository.get_or_create_demo_session(user_id).payment_order_id)

    assert len(set(order_ids)) == 2


def test_pay_flask_landing_page_exposes_demo_boundaries() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True).lower()
    assert "ecloe pay" in body
    assert "simulated payments demo" in body
    assert "does not create real users" in body
    assert "process real money" in body
    assert "/pay/login" in body


def test_pay_flask_landing_adapts_to_accept_language() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/", headers={"Accept-Language": "pt-BR,pt;q=0.9"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'lang="pt-BR"' in body
    assert "Demo de pagamentos simulados" in body
    assert "nao cria usuarios reais" in body
    locale_cookie = client.get_cookie(LOCALE_COOKIE_NAME)
    assert locale_cookie is not None
    assert locale_cookie.value == "pt-BR"


def test_pay_flask_landing_query_locale_overrides_header() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/?lang=pt-BR", headers={"Accept-Language": "en-US,en;q=0.9"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'lang="pt-BR"' in body
    assert "Abrir demo da carteira" in body


def test_pay_flask_landing_unknown_locale_falls_back_to_english() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/", headers={"Accept-Language": "fr-FR,fr;q=0.9"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'lang="en-US"' in body
    assert "Simulated payments demo" in body


def test_pay_flask_wallet_requires_login_on_entry() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/pay")

    assert response.status_code == 302
    assert response.headers["Location"] == "/pay/login?lang=en-US"


def test_pay_flask_wallet_runs_on_pay_route_after_login() -> None:
    app = create_app()
    client = authenticated_client(app)

    response = client.get("/pay")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Demo balance" in body
    assert "Security confirmation" in body
    assert "ECloe Pay demo terms" in body
    assert "Presentation mode" in body


def test_pay_flask_session_requires_login_by_default() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/api/session")

    assert response.status_code == 401


def test_pay_flask_session_exposes_demo_boundaries_after_login() -> None:
    app = create_app()
    client = authenticated_client(app)

    response = client.get("/api/session")

    assert response.status_code == 200
    body = response.get_json()
    assert body["security"]["user_creation_allowed"] is False
    assert body["security"]["real_money_processed"] is False
    assert body["security"]["bucket_name"] == DEMO_BUCKET_NAME
    assert body["security"]["database_provider"] == "memory"
    assert body["security"]["database_schema"] == "ecloe_pay"
    assert body["recommendation"]["decision_id"].startswith("dec_")
    assert body["recommendation"]["policy"] == "deterministic_baseline"
    assert body["benefit"]["offer_id"] == "cashback_recurring_purchase"
    assert body["session"]["selected_decision_id"] == body["recommendation"]["decision_id"]
    assert body["session"]["payment_amount_cents"] == 12790
    assert body["session"]["payment_order_id"] == "pay_order_demo_7841"
    assert body["wallet"]["demo_balance_cents"] == 50000
    assert body["wallet"]["cashback_cents"] == 0
    assert body["wallet"]["currency"] == "BRL"
    assert body["loan_requests"]
    loan_request = body["loan_requests"][0]
    assert loan_request["loan_request_id"].startswith("loan_req_")
    assert loan_request["requested_amount_cents"] > 0
    assert loan_request["currency"] == "BRL"
    assert loan_request["status"] in {"requested", "under_review", "cancelled"}
    assert "credit decision" in loan_request["synthetic_notice"]


def test_pay_flask_requires_terms_before_interaction() -> None:
    app = create_app()
    client = authenticated_client(app)
    client.get("/pay")

    response = client.post(
        "/api/benefit-interactions",
        json={"action": "accept"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "Demo terms are required before recording interactions."


def test_pay_flask_accepts_terms_and_simulates_payment_once() -> None:
    app = create_app()
    client = authenticated_client(app)
    client.get("/pay")

    terms_response = client.post("/api/terms", json={"accepted": True}, headers=csrf_headers(client))
    payment_response = client.post(
        "/api/payment-orders/pay_order_demo_7841/simulate",
        json={"confirmation_code": "0426"},
        headers=csrf_headers(client),
    )
    duplicate_response = client.post(
        "/api/payment-orders/pay_order_demo_7841/simulate",
        json={"confirmation_code": "0426"},
        headers=csrf_headers(client),
    )

    assert terms_response.status_code == 200
    assert payment_response.status_code == 200
    body = payment_response.get_json()
    assert body["status"] == "verified"
    assert body["database_provider"] == "memory"
    assert body["database_schema"] == "ecloe_pay"
    assert body["bucket_name"] == DEMO_BUCKET_NAME
    assert body["reward_event"]["event_type"] == "conversion"
    assert duplicate_response.status_code == 409


def test_pay_flask_login_logout_flow() -> None:
    app = create_app()
    client = app.test_client()
    client.get("/pay/login")

    invalid = client.post(
        "/api/auth/login",
        json={"email": SHARED_DEMO_USER_EMAIL, "password": "wrong"},
        headers=csrf_headers(client),
    )
    missing = client.post(
        "/api/auth/login",
        json={"email": "missing.pay@ecloe.local", "password": "wrong"},
        headers=csrf_headers(client),
    )
    valid = client.post(
        "/api/auth/login",
        json={"email": " DEMO.MARKET@ECLOE.LOCAL ", "password": "change-this-demo-password"},
        headers=csrf_headers(client),
    )

    assert invalid.status_code == 401
    assert missing.status_code == 401
    assert invalid.get_json() == missing.get_json()
    assert valid.status_code == 200
    auth_cookie = client.get_cookie(AUTH_COOKIE_NAME)
    assert auth_cookie is not None
    assert auth_cookie.http_only is True
    assert auth_cookie.same_site == "Lax"
    assert auth_cookie.secure is False
    assert "demo.market" not in auth_cookie.value
    assert "change-this-demo-password" not in auth_cookie.value
    csrf_cookie = client.get_cookie(CSRF_COOKIE_NAME)
    assert csrf_cookie is not None
    assert csrf_cookie.http_only is False
    me = client.get("/api/auth/me")
    logout = client.post("/api/auth/logout", json={}, headers=csrf_headers(client))
    assert valid.get_json()["user"]["email"] == SHARED_DEMO_USER_EMAIL
    assert me.status_code == 200
    assert logout.status_code == 200
    assert client.get_cookie(AUTH_COOKIE_NAME) is None


def test_pay_flask_login_uses_configured_demo_credentials(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_PAY_DEMO_USER_EMAIL", "custom.demo@ecloe.local")
    monkeypatch.setenv("ECLOE_PAY_DEMO_USER_PASSWORD", "configured-demo-secret")
    settings = load_settings(use_env_file=False)
    app = create_app(settings=settings)
    client = app.test_client()
    client.get("/pay/login")

    default_login = client.post(
        "/api/auth/login",
        json={"email": SHARED_DEMO_USER_EMAIL, "password": "change-this-demo-password"},
        headers=csrf_headers(client),
    )
    configured_login = client.post(
        "/api/auth/login",
        json={"email": "custom.demo@ecloe.local", "password": "configured-demo-secret"},
        headers=csrf_headers(client),
    )

    assert default_login.status_code == 401
    assert configured_login.status_code == 200
    assert configured_login.get_json()["user"]["email"] == "custom.demo@ecloe.local"


def test_pay_login_page_has_demo_identity_copy_without_credentials() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/pay/login?lang=pt-BR")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Identidade demonstrativa - nenhuma conta bancaria real" in body
    assert "Azure SQL" in body
    assert SHARED_DEMO_USER_EMAIL not in body
    assert LEGACY_PAY_DEMO_USER_EMAIL not in body
    assert "change-this-demo-password" not in body


def test_pay_login_page_clears_existing_auth_session() -> None:
    app = create_app()
    client = authenticated_client(app)
    auth_cookie = client.get_cookie(AUTH_COOKIE_NAME)
    assert auth_cookie is not None

    response = client.get("/pay/login")

    assert response.status_code == 200
    assert client.get_cookie(AUTH_COOKIE_NAME) is None
    assert client.get("/api/auth/me").status_code == 401


def test_pay_flask_mutating_routes_require_csrf_token() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/auth/login",
        json={"email": SHARED_DEMO_USER_EMAIL, "password": "wrong"},
    )

    assert response.status_code == 403


def test_pay_flask_replaces_client_supplied_csrf_cookie() -> None:
    app = create_app()
    client = app.test_client()
    client.set_cookie(CSRF_COOKIE_NAME, "client-controlled-token")

    response = client.get("/pay/login")

    assert response.status_code == 200
    csrf_cookie = client.get_cookie(CSRF_COOKIE_NAME)
    assert csrf_cookie is not None
    assert csrf_cookie.value != "client-controlled-token"


def test_pay_flask_limits_login_attempts_by_ip_and_email() -> None:
    app = create_app()
    client = app.test_client()
    client.get("/pay/login")

    responses = [
        client.post(
            "/api/auth/login",
            json={"email": SHARED_DEMO_USER_EMAIL, "password": "wrong"},
            headers=csrf_headers(client),
        )
        for _ in range(6)
    ]

    assert [response.status_code for response in responses[:5]] == [401, 401, 401, 401, 401]
    assert responses[5].status_code == 429


def test_pay_flask_pay_route_redirects_to_login_by_default() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/pay")

    assert response.status_code == 302
    assert response.headers["Location"] == "/pay/login?lang=en-US"


def test_pay_flask_rejects_expired_session() -> None:
    app = create_app()
    repository: MemoryPayRepository = app.pay_repository  # type: ignore[attr-defined]
    user = repository.authenticate(SHARED_DEMO_USER_EMAIL, "change-this-demo-password")
    assert user is not None
    auth_session = repository.create_auth_session(user.user_id)
    auth_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    client = app.test_client()
    client.set_cookie(AUTH_COOKIE_NAME, auth_session.auth_session_id)

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_pay_flask_rejects_revoked_session_token() -> None:
    app = create_app()
    repository: MemoryPayRepository = app.pay_repository  # type: ignore[attr-defined]
    user = repository.authenticate(SHARED_DEMO_USER_EMAIL, "change-this-demo-password")
    assert user is not None
    auth_session = repository.create_auth_session(user.user_id)
    repository.revoke_auth_session(auth_session.auth_session_id)
    client = app.test_client()
    client.set_cookie(AUTH_COOKIE_NAME, auth_session.auth_session_id)

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_pay_flask_reset_requires_authentication() -> None:
    app = create_app()
    client = app.test_client()
    client.get("/pay/login")

    response = client.post("/api/reset", json={}, headers=csrf_headers(client))

    assert response.status_code == 401


def test_memory_pay_repository_rolls_back_payment_state_when_outbox_fails() -> None:
    app = create_app()
    repository: MemoryPayRepository = app.pay_repository  # type: ignore[attr-defined]
    user = repository.get_user_by_email(SHARED_DEMO_USER_EMAIL)
    assert user is not None
    session = repository.get_or_create_demo_session(user.user_id)
    repository.accept_terms(session.session_id)

    original_insert_outbox = repository._insert_outbox

    def fail_payment_verified(*args, **kwargs):
        if args[2] == "payment_verified":
            raise RuntimeError("forced outbox failure")
        return original_insert_outbox(*args, **kwargs)

    repository._insert_outbox = fail_payment_verified  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="forced outbox failure"):
        repository.simulate_payment(session.session_id, "0426")

    restored = repository.get_demo_session(session.session_id)
    assert restored is not None
    assert restored.payment_status == "created"
    assert repository.benefit_events[session.session_id] == []
    assert repository.outbox_events == []
