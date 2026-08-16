from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from src.core.config import load_settings
from src.demo.ecloe_pay.app import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, create_app
from src.demo.ecloe_pay.repositories import (
    LEGACY_PAY_DEMO_USER_EMAIL,
    SHARED_DEMO_USER_EMAIL,
    PayRepository,
)
from src.demo.ecloe_pay.repositories.memory import MemoryPayRepository


def csrf_headers(client) -> dict[str, str]:
    cookie = client.get_cookie(CSRF_COOKIE_NAME)
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def authenticated_client(repository: PayRepository, password: str = "change-this-demo-password"):
    app = create_app(repository=repository)
    client = app.test_client()
    client.get("/pay/login")
    response = client.post(
        "/api/auth/login",
        json={"email": SHARED_DEMO_USER_EMAIL, "password": password},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200
    return client


@pytest.fixture(params=["memory", "azure_sql"], ids=["memory", "azure_sql_optional"])
def repository_contract(request, monkeypatch) -> Iterator[tuple[PayRepository, str]]:
    if request.param == "memory":
        settings = load_settings(use_env_file=False)
        repository = MemoryPayRepository(settings)
        repository.requires_authentication = True
        yield repository, settings.ecloe_pay_demo_user_password
        return

    if os.getenv("ECLOE_PAY_SQL_CONTRACT_TESTS") != "1":
        pytest.skip("Set ECLOE_PAY_SQL_CONTRACT_TESTS=1 to run Azure SQL contract tests.")

    monkeypatch.setenv("ECLOE_PAY_DATABASE_MODE", "azure_sql")
    settings = load_settings(use_env_file=False)
    from src.demo.ecloe_pay.repositories.azure_sql import AzureSqlPayRepository

    repository = AzureSqlPayRepository(settings)
    if not repository.health_check():
        pytest.skip("Configured Azure SQL test database is not healthy.")
    yield repository, settings.ecloe_pay_demo_user_password


def test_pay_contract_login_session_logout_and_revoked_token(repository_contract) -> None:
    repository, password = repository_contract
    app = create_app(repository=repository)
    client = app.test_client()
    client.get("/pay/login")

    invalid = client.post(
        "/api/auth/login",
        json={"email": SHARED_DEMO_USER_EMAIL, "password": "wrong"},
        headers=csrf_headers(client),
    )
    valid = client.post(
        "/api/auth/login",
        json={"email": SHARED_DEMO_USER_EMAIL, "password": password},
        headers=csrf_headers(client),
    )

    assert invalid.status_code == 401
    assert valid.status_code == 200
    auth_cookie = client.get_cookie(AUTH_COOKIE_NAME)
    assert auth_cookie is not None
    assert auth_cookie.http_only is True
    assert "demo.market" not in auth_cookie.value
    assert password not in auth_cookie.value
    assert client.get("/api/auth/me").status_code == 200

    logout = client.post("/api/auth/logout", json={}, headers=csrf_headers(client))

    assert logout.status_code == 200
    assert client.get_cookie(AUTH_COOKIE_NAME) is None
    assert client.get("/api/auth/me").status_code == 401


def test_pay_contract_accepts_legacy_pay_demo_identity(repository_contract) -> None:
    repository, password = repository_contract
    app = create_app(repository=repository)
    client = app.test_client()
    client.get("/pay/login")

    response = client.post(
        "/api/auth/login",
        json={"email": LEGACY_PAY_DEMO_USER_EMAIL, "password": password},
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == LEGACY_PAY_DEMO_USER_EMAIL


def test_pay_contract_terms_interaction_payment_idempotency_and_reset(repository_contract) -> None:
    repository, password = repository_contract
    client = authenticated_client(repository, password)

    before_terms = client.post(
        "/api/benefit-interactions",
        json={"action": "accept"},
        headers=csrf_headers(client),
    )
    terms = client.post("/api/terms", json={"accepted": True}, headers=csrf_headers(client))
    interaction = client.post(
        "/api/benefit-interactions",
        json={"action": "open"},
        headers=csrf_headers(client),
    )
    payment = client.post(
        "/api/payment-orders/pay_order_demo_7841/simulate",
        json={"confirmation_code": "0426"},
        headers=csrf_headers(client),
    )
    duplicate = client.post(
        "/api/payment-orders/pay_order_demo_7841/simulate",
        json={"confirmation_code": "0426"},
        headers=csrf_headers(client),
    )
    reset = client.post("/api/reset", json={}, headers=csrf_headers(client))

    assert before_terms.status_code == 403
    assert terms.status_code == 200
    assert interaction.status_code == 200
    assert interaction.get_json()["reward_event"]["event_type"] == "open"
    assert payment.status_code == 200
    assert payment.get_json()["status"] == "verified"
    assert duplicate.status_code == 409
    assert reset.status_code == 200


def test_pay_contract_protected_routes_require_authentication(repository_contract) -> None:
    repository, _ = repository_contract
    client = create_app(repository=repository).test_client()
    client.get("/pay/login")

    assert client.get("/api/session").status_code == 401
    assert client.post("/api/terms", json={"accepted": True}, headers=csrf_headers(client)).status_code == 401
    assert (
        client.post(
            "/api/benefit-interactions",
            json={"action": "open"},
            headers=csrf_headers(client),
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/payment-orders/pay_order_demo_7841/simulate",
            json={"confirmation_code": "0426"},
            headers=csrf_headers(client),
        ).status_code
        == 401
    )
    assert client.post("/api/reset", json={}, headers=csrf_headers(client)).status_code == 401
