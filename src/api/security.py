from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from importlib.util import find_spec
from typing import Any

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes

from src.api.schemas.errors import ErrorCode, ErrorResponse
from src.core.config import Settings


CLOUD_ENVIRONMENTS = {"cloud", "prod", "production", "azure"}
LOCAL_HOSTS = {"127.0.0.1"}
SUPPORTED_AUTH_MODES = {"disabled", "entra_id"}
SUPPORTED_DECISION_REPOSITORY_MODES = {"memory", "file", "cosmos"}
REQUIRED_ENTRA_SETTINGS = {"entra_tenant_id", "entra_client_id", "entra_audience"}
AVAILABLE_SCOPES = frozenset({"decision:write", "decision:read", "reward:write", "policy:read"})
LOCAL_SUBJECT_KEY_SALT = "local-dev-subject-key-salt"

bearer_scheme = HTTPBearer(auto_error=False)


class SecurityConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    subject: str
    scopes: frozenset[str]
    claims: dict[str, Any]


def validate_security_settings(settings: Settings) -> None:
    if settings.auth_mode not in SUPPORTED_AUTH_MODES:
        raise SecurityConfigurationError(f"Unsupported AUTH_MODE: {settings.auth_mode}")
    if settings.decision_repository_mode not in SUPPORTED_DECISION_REPOSITORY_MODES:
        raise SecurityConfigurationError(
            f"Unsupported DECISION_REPOSITORY_MODE: {settings.decision_repository_mode}"
        )

    is_cloud = settings.app_environment in CLOUD_ENVIRONMENTS
    if "*" in settings.cors_allowed_origins:
        raise SecurityConfigurationError("CORS_ALLOWED_ORIGINS must not contain wildcard origins.")
    if is_cloud and "*" in settings.trusted_hosts:
        raise SecurityConfigurationError("TRUSTED_HOSTS must not contain wildcard hosts in cloud.")

    if settings.auth_mode == "disabled" and (
        is_cloud or settings.api_host not in LOCAL_HOSTS
    ):
        raise SecurityConfigurationError(
            "AUTH_MODE=disabled is allowed only for local loopback execution."
        )

    if is_cloud:
        if settings.subject_key_salt == LOCAL_SUBJECT_KEY_SALT:
            raise SecurityConfigurationError(
                "Cloud environments must configure a non-default SUBJECT_KEY_SALT."
            )
        if settings.azure_cosmos_key:
            raise SecurityConfigurationError(
                "Permanent AZURE_COSMOS_KEY is not allowed in cloud environments."
            )
        if settings.azure_cosmos_auth_mode != "managed_identity":
            raise SecurityConfigurationError(
                "Cloud environments must use AZURE_COSMOS_AUTH_MODE=managed_identity."
            )
        if settings.decision_repository_mode != "cosmos":
            raise SecurityConfigurationError(
                "Cloud environments must use DECISION_REPOSITORY_MODE=cosmos."
            )

    if settings.auth_mode == "entra_id":
        missing = [
            name
            for name in REQUIRED_ENTRA_SETTINGS
            if not getattr(settings, name)
        ]
        if missing:
            raise SecurityConfigurationError(
                f"Missing Microsoft Entra ID settings: {sorted(missing)}"
            )
        if find_spec("jwt") is None:
            raise SecurityConfigurationError("PyJWT[crypto] is required for AUTH_MODE=entra_id.")


def require_scopes(*required_scopes: str):
    unknown = sorted(set(required_scopes) - AVAILABLE_SCOPES)
    if unknown:
        raise SecurityConfigurationError(f"Unknown API scopes configured: {unknown}")

    async def dependency(
        security_scopes: SecurityScopes,
        credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
        settings: Settings = Depends(_settings),
    ) -> Principal:
        route_scopes = set(security_scopes.scopes) if security_scopes is not None else set()
        all_required = set(required_scopes) | route_scopes
        if settings.auth_mode == "disabled":
            validate_security_settings(settings)
            return Principal(subject="local-dev", scopes=frozenset(all_required), claims={})

        if credentials is None or credentials.scheme.lower() != "bearer":
            raise _auth_error("Missing bearer token")

        principal = validate_entra_token(credentials.credentials, settings)
        missing = sorted(all_required - principal.scopes)
        if missing:
            raise _auth_error(f"Missing required scopes: {missing}", status_code=403)
        return principal

    dependency.required_scopes = frozenset(required_scopes)  # type: ignore[attr-defined]
    return dependency


def validate_entra_token(token: str, settings: Settings) -> Principal:
    try:
        import jwt
        from jwt import PyJWKClient
    except ModuleNotFoundError as error:
        raise SecurityConfigurationError("PyJWT[crypto] is required for AUTH_MODE=entra_id.") from error

    jwks_url = settings.entra_jwks_url or (
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/v2.0/keys"
    )
    issuer = settings.entra_issuer or (
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
    )

    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.entra_audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except Exception as error:
        raise _auth_error("Invalid bearer token") from error

    scopes = _extract_scopes(claims)
    subject = str(claims.get("sub") or claims.get("oid") or "")
    if not subject:
        raise _auth_error("Token subject is missing")
    return Principal(subject=subject, scopes=frozenset(scopes), claims=claims)


def subject_key_for(principal: Principal, settings: Settings) -> str:
    digest = hmac.new(
        settings.subject_key_salt.encode("utf-8"),
        principal.subject.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sub_{digest}"


def _extract_scopes(claims: dict[str, Any]) -> set[str]:
    scope_claim = claims.get("scp", "")
    roles_claim = claims.get("roles", [])
    scopes = set(str(scope_claim).split())
    if isinstance(roles_claim, list):
        scopes.update(str(role) for role in roles_claim)
    return scopes


def _settings() -> Settings:
    from src.core.config import load_settings

    return load_settings()


def _auth_error(message: str, status_code: int = 401) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    code = ErrorCode.unauthorized if status_code == 401 else ErrorCode.forbidden
    return HTTPException(
        status_code=status_code,
        detail=ErrorResponse(code=code, message=message).model_dump(mode="json"),
        headers=headers,
    )
