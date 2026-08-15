from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.core.config import load_settings
from src.demo.ecloe_pay.app import (
    AUTH_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    OIDC_FLOW_COOKIE_NAME,
    create_app,
)
from src.demo.ecloe_pay.identity import EntraExternalIdentity, safe_return_to, subject_key
from src.demo.ecloe_pay.personas import load_personas, persona_for_subject
from src.demo.ecloe_pay.repositories.base import OidcLoginFlow, SignupIpLimitExceeded
from src.demo.ecloe_pay.repositories.memory import MemoryPayRepository


class FakeOAuthClient:
    def __init__(self, *, subject: str = "external-subject-123") -> None:
        self.subject = subject
        self.prompts: list[str | None] = []

    def initiate_auth_code_flow(self, scopes, redirect_uri, prompt=None):
        assert scopes == []
        self.prompts.append(prompt)
        return {
            "auth_uri": "https://tenant.ciamlogin.com/authorize?state=state-123",
            "state": "state-123",
            "nonce": "nonce-123",
            "code_verifier": "verifier-123",
            "redirect_uri": redirect_uri,
        }

    def acquire_token_by_auth_code_flow(self, auth_code_flow, auth_response):
        if auth_response.get("state") != auth_code_flow["state"]:
            return {"error": "state_mismatch"}
        return {
            "access_token": "must-not-be-persisted",
            "id_token": "must-not-be-persisted",
            "id_token_claims": {
                "iss": "https://tenant.ciamlogin.com/v2.0",
                "sub": self.subject,
                "email": "real.customer@example.com",
                "name": "Real Customer Name",
            },
        }


def external_settings():
    return replace(
        load_settings(use_env_file=False),
        ecloe_web_auth_mode="entra_external",
        ecloe_web_entra_authority="https://tenant.ciamlogin.com",
        ecloe_web_entra_client_id="client-id",
        ecloe_web_entra_client_secret="client-secret",
        ecloe_web_entra_redirect_uri="https://demo.example/auth/callback",
        ecloe_web_entra_post_logout_redirect_uri="https://demo.example/",
    )


def test_external_login_provisions_only_synthetic_data_and_opaque_session() -> None:
    settings = external_settings()
    repository = MemoryPayRepository(settings)
    client = create_app(
        settings=settings, repository=repository, identity_client=FakeOAuthClient()
    ).test_client()

    start = client.get("/auth/login?return_to=/market/orders")
    assert start.status_code == 302
    assert start.headers["Location"].startswith("https://tenant.ciamlogin.com/")

    callback = client.get("/auth/callback?state=state-123&code=code-123")
    assert callback.status_code == 302
    assert callback.headers["Location"] == "/market/orders"
    auth_cookie = client.get_cookie(AUTH_COOKIE_NAME)
    assert auth_cookie is not None and auth_cookie.http_only
    assert "external-subject" not in auth_cookie.value

    me = client.get("/api/auth/me").get_json()
    assert me["authenticated"] is True
    assert me["auth_provider"] == "entra_external"
    assert me["user"]["email"].endswith("@demo.ecloe.local")
    serialized = repr(repository.users) + repr(repository.profiles) + repr(repository.accounts)
    assert "real.customer@example.com" not in serialized
    assert "Real Customer Name" not in serialized
    assert "must-not-be-persisted" not in serialized

    session = client.get("/api/session").get_json()
    assert session["profile"]["market_segment"]
    assert session["account"]["currency"] == "BRL"
    assert session["account"]["available_balance_cents"] == 50000
    assert session["account"]["transactions"][0]["amount_cents"] == 50000


def test_oidc_flow_is_single_use_and_rejects_external_return_url() -> None:
    settings = external_settings()
    repository = MemoryPayRepository(settings)
    identity = EntraExternalIdentity(settings, FakeOAuthClient())
    identity.begin(repository, "flow-secret", "https://attacker.example/steal")

    first = identity.complete(repository, "flow-secret", {"state": "state-123", "code": "ok"})
    second = identity.complete(repository, "flow-secret", {"state": "state-123", "code": "ok"})

    assert first is not None and first[1] == "/pay"
    assert second is None
    assert safe_return_to("//attacker.example") == "/pay"
    assert safe_return_to("/market/products/demo") == "/market/products/demo"
    assert safe_return_to("/pay/") == "/pay"
    assert safe_return_to("/market/?lang=pt-BR") == "/market?lang=pt-BR"


def test_expired_oidc_flow_and_idle_session_are_rejected() -> None:
    settings = external_settings()
    repository = MemoryPayRepository(settings)
    repository.store_oidc_flow(
        OidcLoginFlow(
            flow_id="expired-flow",
            payload={},
            return_to="/pay",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    assert repository.consume_oidc_flow("expired-flow") is None

    user = repository.provision_external_user("issuer", "subject-key")
    assert user is not None
    session = repository.create_auth_session(user.user_id)
    session.idle_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert repository.get_auth_session(session.auth_session_id) is None


def test_external_provisioning_is_deterministic_and_idempotent() -> None:
    settings = external_settings()
    repository = MemoryPayRepository(settings)
    key = subject_key(settings, "https://tenant.ciamlogin.com/v2.0", "same-subject")

    first = repository.provision_external_user(
        "https://tenant.ciamlogin.com/v2.0",
        key,
        signup_ip_hash="hashed-ip",
    )
    second = repository.provision_external_user(
        "https://tenant.ciamlogin.com/v2.0",
        key,
        signup_ip_hash="hashed-ip",
    )

    assert first == second
    assert len(repository.external_identities) == 1
    assert len(repository.signup_registrations) == 1
    assert len(load_personas()) >= 4
    assert persona_for_subject(key) == persona_for_subject(key)

    demo_session = repository.get_or_create_demo_session(first.user_id)
    original_account = repository.synthetic_account(first.user_id)
    repository.accounts[first.user_id] = replace(original_account, available_balance_cents=1)
    repository.reset_demo_state(demo_session.session_id)
    assert repository.synthetic_account(first.user_id) == original_account


def test_signup_route_uses_create_prompt_and_login_page_links_signup() -> None:
    settings = external_settings()
    repository = MemoryPayRepository(settings)
    oauth_client = FakeOAuthClient()
    client = create_app(
        settings=settings, repository=repository, identity_client=oauth_client
    ).test_client()

    login_page = client.get("/pay/login?return_to=/pay&lang=pt-BR")
    assert login_page.status_code == 200
    assert b"/auth/signup?return_to=%2Fpay" in login_page.data
    assert b"Criar conta" in login_page.data

    signup = client.get("/auth/signup?return_to=/pay")

    assert signup.status_code == 302
    assert oauth_client.prompts == ["create"]


def test_signup_ip_limit_blocks_second_new_subject_and_clears_oidc_cookie() -> None:
    settings = external_settings()
    repository = MemoryPayRepository(settings)
    first_oauth = FakeOAuthClient(subject="subject-one")
    client = create_app(
        settings=settings, repository=repository, identity_client=first_oauth
    ).test_client()

    client.get("/auth/signup", headers={"X-Forwarded-For": "198.51.100.7"})
    assert client.get_cookie(OIDC_FLOW_COOKIE_NAME, path="/auth/callback") is not None
    first = client.get(
        "/auth/callback?state=state-123&code=code-123",
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert first.status_code == 302

    app = client.application
    app.external_identity = EntraExternalIdentity(  # type: ignore[attr-defined]
        settings,
        FakeOAuthClient(subject="subject-two"),
    )
    client.get("/auth/signup", headers={"X-Forwarded-For": "198.51.100.7"})
    blocked = client.get(
        "/auth/callback?state=state-123&code=code-123",
        headers={"X-Forwarded-For": "198.51.100.7"},
    )

    assert blocked.status_code == 403
    assert blocked.get_json()["error"] == "This IP address has already created an ECloe account."
    assert client.get_cookie(OIDC_FLOW_COOKIE_NAME, path="/auth/callback") is None
    assert len(repository.external_identities) == 1
    persisted = repr(repository.signup_registrations)
    assert "198.51.100.7" not in persisted
    assert "blocked_ip_limit" in persisted


def test_signup_allowlisted_ip_can_create_multiple_accounts() -> None:
    settings = replace(
        external_settings(),
        ecloe_signup_admin_ip_allowlist=("198.51.100.7",),
    )
    repository = MemoryPayRepository(settings)

    first = repository.provision_external_user(
        "https://tenant.ciamlogin.com/v2.0",
        "subject-one",
        signup_ip_hash="hashed-ip",
        allow_ip_reuse=True,
    )
    second = repository.provision_external_user(
        "https://tenant.ciamlogin.com/v2.0",
        "subject-two",
        signup_ip_hash="hashed-ip",
        allow_ip_reuse=True,
    )

    assert first is not None
    assert second is not None
    assert first.user_id != second.user_id
    assert len(repository.external_identities) == 2


def test_signup_ip_limit_exception_is_raised_for_repository_race_guard() -> None:
    settings = external_settings()
    repository = MemoryPayRepository(settings)
    repository.provision_external_user(
        "https://tenant.ciamlogin.com/v2.0",
        "subject-one",
        signup_ip_hash="hashed-ip",
    )

    with pytest.raises(SignupIpLimitExceeded):
        repository.provision_external_user(
            "https://tenant.ciamlogin.com/v2.0",
            "subject-two",
            signup_ip_hash="hashed-ip",
        )


def test_logout_revokes_local_session_and_returns_entra_logout_url() -> None:
    settings = external_settings()
    repository = MemoryPayRepository(settings)
    client = create_app(
        settings=settings, repository=repository, identity_client=FakeOAuthClient()
    ).test_client()
    client.get("/auth/login")
    client.get("/auth/callback?state=state-123&code=code-123")
    csrf = client.get_cookie(CSRF_COOKIE_NAME)
    assert csrf is not None

    response = client.post(
        "/api/auth/logout", json={}, headers={"X-CSRF-Token": csrf.value}
    )

    assert response.status_code == 200
    assert response.get_json()["logout_url"].startswith("https://tenant.ciamlogin.com/")
    assert client.get_cookie(AUTH_COOKIE_NAME) is None
    assert client.get("/api/auth/me").status_code == 401


def test_cloud_demo_rejects_local_authentication_and_memory_state() -> None:
    settings = replace(load_settings(use_env_file=False), app_environment="cloud")
    with pytest.raises(ValueError, match="ECLOE_WEB_AUTH_MODE=entra_external"):
        create_app(settings=settings)
