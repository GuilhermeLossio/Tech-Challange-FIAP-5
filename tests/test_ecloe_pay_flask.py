from datetime import UTC, datetime, timedelta

import pytest

from src.demo.ecloe_pay.app import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, create_app
from src.demo.ecloe_pay.repositories import DEMO_BUCKET_NAME, MemoryPayRepository


def csrf_headers(client) -> dict[str, str]:
    cookie = client.get_cookie(CSRF_COOKIE_NAME)
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


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
    assert "/pay" in body


def test_pay_flask_wallet_runs_on_pay_route() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/pay")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Demo balance" in body
    assert "Security confirmation" in body
    assert "ECloe Pay demo terms" in body
    assert "Presentation mode — data is not being persisted." in body


def test_pay_flask_session_exposes_demo_boundaries() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/api/session")

    assert response.status_code == 200
    body = response.get_json()
    assert body["security"]["user_creation_allowed"] is False
    assert body["security"]["real_money_processed"] is False
    assert body["security"]["bucket_name"] == DEMO_BUCKET_NAME
    assert body["security"]["database_provider"] == "memory"
    assert body["security"]["database_schema"] == "ecloe_pay"


def test_pay_flask_requires_terms_before_interaction() -> None:
    app = create_app()
    client = app.test_client()
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
    client = app.test_client()
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
        json={"email": "demo.pay@ecloe.local", "password": "wrong"},
        headers=csrf_headers(client),
    )
    missing = client.post(
        "/api/auth/login",
        json={"email": "missing.pay@ecloe.local", "password": "wrong"},
        headers=csrf_headers(client),
    )
    valid = client.post(
        "/api/auth/login",
        json={"email": " DEMO.PAY@ECLOE.LOCAL ", "password": "change-this-demo-password"},
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
    assert "demo.pay" not in auth_cookie.value
    assert "change-this-demo-password" not in auth_cookie.value
    csrf_cookie = client.get_cookie(CSRF_COOKIE_NAME)
    assert csrf_cookie is not None
    assert csrf_cookie.http_only is False
    me = client.get("/api/auth/me")
    logout = client.post("/api/auth/logout", json={}, headers=csrf_headers(client))
    assert valid.get_json()["user"]["email"] == "demo.pay@ecloe.local"
    assert me.status_code == 200
    assert logout.status_code == 200
    assert client.get_cookie(AUTH_COOKIE_NAME) is None


def test_pay_login_page_has_demo_identity_copy() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/pay/login")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Identidade demonstrativa — nenhuma conta bancária real" in body
    assert "Azure SQL-backed sessions" in body


def test_pay_flask_mutating_routes_require_csrf_token() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post("/api/auth/login", json={"email": "demo.pay@ecloe.local", "password": "wrong"})

    assert response.status_code == 403


def test_pay_flask_limits_login_attempts_by_ip_and_email() -> None:
    app = create_app()
    client = app.test_client()
    client.get("/pay/login")

    responses = [
        client.post(
            "/api/auth/login",
            json={"email": "demo.pay@ecloe.local", "password": "wrong"},
            headers=csrf_headers(client),
        )
        for _ in range(6)
    ]

    assert [response.status_code for response in responses[:5]] == [401, 401, 401, 401, 401]
    assert responses[5].status_code == 429


def test_pay_flask_azure_sql_mode_requires_login(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "memory")
    app = create_app()
    repository: MemoryPayRepository = app.pay_repository  # type: ignore[attr-defined]
    repository.requires_authentication = True
    client = app.test_client()

    response = client.get("/api/session")

    assert response.status_code == 401


def test_pay_flask_azure_sql_mode_redirects_pay_to_login(monkeypatch) -> None:
    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "memory")
    app = create_app()
    repository: MemoryPayRepository = app.pay_repository  # type: ignore[attr-defined]
    repository.requires_authentication = True
    client = app.test_client()

    response = client.get("/pay")

    assert response.status_code == 302
    assert response.headers["Location"] == "/pay/login"


def test_pay_flask_rejects_expired_session() -> None:
    app = create_app()
    repository: MemoryPayRepository = app.pay_repository  # type: ignore[attr-defined]
    repository.requires_authentication = True
    user = repository.authenticate("demo.pay@ecloe.local", "change-this-demo-password")
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
    repository.requires_authentication = True
    user = repository.authenticate("demo.pay@ecloe.local", "change-this-demo-password")
    assert user is not None
    auth_session = repository.create_auth_session(user.user_id)
    repository.revoke_auth_session(auth_session.auth_session_id)
    client = app.test_client()
    client.set_cookie(AUTH_COOKIE_NAME, auth_session.auth_session_id)

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_pay_flask_reset_requires_authentication() -> None:
    app = create_app()
    repository: MemoryPayRepository = app.pay_repository  # type: ignore[attr-defined]
    repository.requires_authentication = True
    client = app.test_client()
    client.get("/pay/login")

    response = client.post("/api/reset", json={}, headers=csrf_headers(client))

    assert response.status_code == 401


def test_memory_pay_repository_rolls_back_payment_state_when_outbox_fails() -> None:
    app = create_app()
    repository: MemoryPayRepository = app.pay_repository  # type: ignore[attr-defined]
    user = repository.get_user_by_email("demo.pay@ecloe.local")
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
