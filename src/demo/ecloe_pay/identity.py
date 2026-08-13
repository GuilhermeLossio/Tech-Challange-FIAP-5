from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

from src.core.config import Settings
from src.demo.ecloe_pay.repositories import OidcLoginFlow, PayRepository

ALLOWED_RETURN_PATHS = ("/", "/pay", "/market", "/demo/summary")


class OAuthClient(Protocol):
    def initiate_auth_code_flow(self, scopes: list[str], redirect_uri: str) -> dict[str, Any]: ...

    def acquire_token_by_auth_code_flow(
        self, auth_code_flow: dict[str, Any], auth_response: dict[str, str]
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CompletedIdentity:
    issuer: str
    subject_key: str


def safe_return_to(value: str | None) -> str:
    candidate = (value or "/pay").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/") or candidate.startswith("//"):
        return "/pay"
    path = parsed.path.rstrip("/") or "/"
    if not any(path == allowed or path.startswith(f"{allowed}/") for allowed in ALLOWED_RETURN_PATHS):
        return "/pay"
    return candidate


def subject_key(settings: Settings, issuer: str, subject: str) -> str:
    message = f"{issuer.strip().lower()}\x00{subject}".encode()
    return hmac.new(settings.subject_key_salt.encode(), message, hashlib.sha256).hexdigest()


class EntraExternalIdentity:
    def __init__(self, settings: Settings, client: OAuthClient | None = None) -> None:
        self.settings = settings
        self.client = client or self._create_client()

    def _create_client(self) -> OAuthClient:
        try:
            import msal
        except ModuleNotFoundError as error:
            raise RuntimeError("Install msal to use ECLOE_WEB_AUTH_MODE=entra_external.") from error
        return msal.ConfidentialClientApplication(
            self.settings.ecloe_web_entra_client_id,
            authority=self.settings.ecloe_web_entra_authority,
            client_credential=self.settings.ecloe_web_entra_client_secret,
        )

    def begin(self, repository: PayRepository, flow_id: str, return_to: str) -> str:
        payload = self.client.initiate_auth_code_flow(
            scopes=[],
            redirect_uri=self.settings.ecloe_web_entra_redirect_uri,
        )
        auth_uri = payload.get("auth_uri")
        if not isinstance(auth_uri, str) or not auth_uri:
            raise RuntimeError("External ID did not return an authorization URI.")
        repository.store_oidc_flow(
            OidcLoginFlow(
                flow_id=flow_id,
                payload=payload,
                return_to=safe_return_to(return_to),
                expires_at=datetime.now(UTC)
                + timedelta(seconds=self.settings.ecloe_web_oidc_flow_ttl_seconds),
            )
        )
        return auth_uri

    def complete(
        self, repository: PayRepository, flow_id: str, response: dict[str, str]
    ) -> tuple[CompletedIdentity, str] | None:
        flow = repository.consume_oidc_flow(flow_id)
        if flow is None:
            return None
        result = self.client.acquire_token_by_auth_code_flow(flow.payload, response)
        claims = result.get("id_token_claims") if isinstance(result, dict) else None
        if not isinstance(claims, dict):
            return None
        issuer = claims.get("iss")
        subject = claims.get("sub")
        if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
            return None
        return CompletedIdentity(issuer, subject_key(self.settings, issuer, subject)), flow.return_to

    def logout_url(self) -> str:
        query = urlencode({"post_logout_redirect_uri": self.settings.ecloe_web_entra_post_logout_redirect_uri})
        return f"{self.settings.ecloe_web_entra_authority}/oauth2/v2.0/logout?{query}"
