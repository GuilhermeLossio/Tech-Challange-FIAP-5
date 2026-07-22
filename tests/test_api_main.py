from __future__ import annotations

import asyncio
from dataclasses import replace
import json

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import pandas as pd
import pytest
from pydantic import ValidationError

fastapi = pytest.importorskip("fastapi")

import src.api.main as api_main  # noqa: E402
from src.api import dependencies  # noqa: E402
from src.api.security import Principal, require_scopes, validate_security_settings  # noqa: E402
from src.api.schemas.decisions import DecisionRequest  # noqa: E402
from src.api.schemas.errors import ErrorResponse  # noqa: E402
from src.core.config import load_settings  # noqa: E402
from src.engine.likelihood import train_likelihood_model  # noqa: E402
from src.engine.service import DecisionService  # noqa: E402
from src.storage.decision_repository import InMemoryDecisionRepository  # noqa: E402


def processed_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": [f"row_{index}" for index in range(9)],
            "recency": [1, 2, 3] * 3,
            "history_segment": ["1) Low", "2) Medium", "3) High"] * 3,
            "mens": [1, 0, 1] * 3,
            "womens": [0, 1, 1] * 3,
            "newbie": [1, 0, 0] * 3,
            "channel": ["Web", "Phone", "Multichannel"] * 3,
            "action": ["mens_email", "womens_email", "no_email"] * 3,
            "reward": [1, 0, 0, 1, 1, 0, 1, 0, 0],
            "visit": [1, 0, 1] * 3,
            "spend": [10.0, 0.0, 0.0] * 3,
        }
    )


def test_api_health() -> None:
    app = api_main.create_app()
    endpoint = route_endpoint(app, "/livez", "GET")

    response = endpoint()

    assert response["status"] == "ok"


def test_api_purchase_likelihood_and_decision(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    model_file = tmp_path / "purchase_likelihood_model.json"
    selected_policy_file = tmp_path / "selected_policy.json"
    processed_dataframe().to_csv(input_file, index=False)
    model = train_likelihood_model(input_file=input_file, output_file=model_file, min_samples=2)
    selected_policy_file.write_text(
        json.dumps(
            {
                "schema_version": "selected_policy.v1",
                "artifact_status": "active",
                "policy": "thompson_sampling",
                "version": "offline-v1",
                "selection_rule": "test fixture",
                "metrics": {"rounds": 9},
            }
        ),
        encoding="utf-8",
    )
    service = DecisionService.from_files(model_file, selected_policy_file)
    repository = InMemoryDecisionRepository()
    principal = Principal("user-1", frozenset({"decision:write", "decision:read", "policy:read"}), {})

    app = api_main.create_app(service, repository)
    payload = {
        "request_id": "req_1",
        "customer_context": {"channel": "Web", "history_segment": "1) Low", "newbie": 1},
        "eligible_offers": ["cashback_recurring_purchase", "financial_education"],
    }
    request = DecisionRequest(**payload)

    likelihood = route_endpoint(app, "/v1/likelihood-estimates", "POST")(request, service=service)
    alias = route_endpoint(app, "/v1/purchase-likelihood", "POST")(request, service=service)
    decision = route_endpoint(app, "/v1/decisions", "POST")(
        request,
        idempotency_key="idem-1",
        principal=principal,
        service=service,
        repository=repository,
        settings=load_settings(),
    )
    repeated = route_endpoint(app, "/v1/decisions", "POST")(
        request,
        idempotency_key="idem-1",
        principal=principal,
        service=service,
        repository=repository,
        settings=load_settings(),
    )
    policy = route_endpoint(app, "/v1/policies/current", "GET")(service=service)

    assert len(likelihood["estimates"]) == 2
    assert alias == likelihood
    assert decision["offer_id"] in payload["eligible_offers"]
    assert decision["policy"] == "likelihood_ranker"
    assert decision["policy_version"] == model.version
    assert decision["artifact_version"] == model.version
    assert decision == repeated
    assert repository.event_count == 1
    assert decision["created_at"]
    assert len(decision["artifact_checksum"]) == 64
    assert policy["policy"] == "likelihood_ranker"
    assert policy["artifact_checksum"] == decision["artifact_checksum"]
    assert policy["promoted_offline_policy"]["policy"] == "thompson_sampling"
    record = repository.records[0]
    assert record.decision_id == decision["decision_id"]
    assert record.request_id == "req_1"
    assert record.selected_offer_id == decision["offer_id"]
    assert record.policy == "likelihood_ranker"
    assert record.policy_version == decision["policy_version"]
    assert record.artifact_checksum == decision["artifact_checksum"]
    assert record.reason_codes == decision["reason_codes"]
    assert record.minimized_context == {"channel": "Web", "history_segment": "1) Low", "newbie": 1}
    assert record.subject_key.startswith("sub_")
    assert record.subject_key != principal.subject
    assert record.ttl == load_settings().decision_event_ttl_seconds


def test_decision_without_idempotency_key_persists_new_events(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    model_file = tmp_path / "purchase_likelihood_model.json"
    selected_policy_file = tmp_path / "selected_policy.json"
    processed_dataframe().to_csv(input_file, index=False)
    train_likelihood_model(input_file=input_file, output_file=model_file, min_samples=2)
    selected_policy_file.write_text(
        json.dumps(
            {
                "schema_version": "selected_policy.v1",
                "artifact_status": "active",
                "policy": "thompson_sampling",
                "version": "offline-v1",
                "selection_rule": "test fixture",
                "metrics": {"rounds": 9},
            }
        ),
        encoding="utf-8",
    )
    service = DecisionService.from_files(model_file, selected_policy_file)
    repository = InMemoryDecisionRepository()
    principal = Principal("user-1", frozenset({"decision:write"}), {})
    app = api_main.create_app(service, repository)
    request = DecisionRequest(
        request_id="req_1",
        customer_context={"channel": "Web", "history_segment": "1) Low", "newbie": 1},
        eligible_offers=["cashback_recurring_purchase", "financial_education"],
    )

    first = route_endpoint(app, "/v1/decisions", "POST")(
        request,
        idempotency_key=None,
        principal=principal,
        service=service,
        repository=repository,
        settings=load_settings(),
    )
    second = route_endpoint(app, "/v1/decisions", "POST")(
        request,
        idempotency_key=None,
        principal=principal,
        service=service,
        repository=repository,
        settings=load_settings(),
    )

    assert first["decision_id"] != second["decision_id"]
    assert repository.event_count == 2


def test_api_startup_fails_when_artifact_is_missing(monkeypatch) -> None:
    def fail_from_files():
        raise FileNotFoundError("missing model artifact")

    monkeypatch.setattr(dependencies.DecisionService, "from_files", staticmethod(fail_from_files))

    async def run_lifespan() -> None:
        app = api_main.create_app()
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(FileNotFoundError, match="missing model artifact"):
        asyncio.run(run_lifespan())


def test_api_schema_rejects_unknown_context_fields() -> None:
    with pytest.raises(ValidationError) as error:
        DecisionRequest(
            request_id="req_1",
            customer_context={"channel": "Web", "zip_code": "12345"},
            eligible_offers=["cashback_recurring_purchase"],
        )

    assert "Extra inputs are not permitted" in str(error.value)


def test_api_schema_rejects_duplicate_offers() -> None:
    with pytest.raises(ValidationError) as error:
        DecisionRequest(
            request_id="req_1",
            customer_context={"channel": "Web"},
            eligible_offers=["cashback_recurring_purchase", "cashback_recurring_purchase"],
        )

    assert "duplicate offers" in str(error.value)


def test_api_schema_rejects_oversized_request() -> None:
    with pytest.raises(ValidationError) as error:
        DecisionRequest(
            request_id="r" * 65,
            customer_context={"channel": "Web"},
            eligible_offers=["cashback_recurring_purchase"],
        )

    assert "at most 64 characters" in str(error.value)


def test_api_schema_rejects_too_many_offers() -> None:
    with pytest.raises(ValidationError) as error:
        DecisionRequest(
            request_id="req_1",
            customer_context={"channel": "Web"},
            eligible_offers=[
                "mens_email",
                "womens_email",
                "no_email",
                "cashback_recurring_purchase",
                "savings_goal",
                "financial_education",
                "account_upgrade",
                "installment_education",
                "credit_limit",
                "personal_loan",
                "cashback_investment",
            ],
        )

    assert "at most 10 items" in str(error.value)


def test_api_routes_have_explicit_response_models() -> None:
    app = api_main.create_app()

    for path, method in [
        ("/livez", "GET"),
        ("/readyz", "GET"),
        ("/v1/policies/current", "GET"),
        ("/v1/likelihood-estimates", "POST"),
        ("/v1/purchase-likelihood", "POST"),
        ("/v1/decisions", "POST"),
    ]:
        route = route_for(app, path, method)
        assert getattr(route, "response_model", None) is not None
        assert route.responses[401]["model"] is ErrorResponse
        assert route.responses[403]["model"] is ErrorResponse
        assert route.responses[422]["model"] is ErrorResponse

    assert route_for(app, "/v1/purchase-likelihood", "POST").deprecated is True


def test_business_routes_require_expected_scopes() -> None:
    app = api_main.create_app()

    expected = {
        ("/v1/policies/current", "GET"): {"policy:read"},
        ("/v1/likelihood-estimates", "POST"): {"decision:read"},
        ("/v1/purchase-likelihood", "POST"): {"decision:read"},
        ("/v1/decisions", "POST"): {"decision:write"},
    }
    for (path, method), scopes in expected.items():
        route = route_for(app, path, method)
        route_scopes = set()
        for dependency in route.dependant.dependencies:
            route_scopes.update(getattr(dependency.call, "required_scopes", frozenset()))

        assert route_scopes == scopes


def test_api_public_documentation_routes_are_disabled() -> None:
    app = api_main.create_app()
    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/openapi.json" not in paths


def test_cloud_security_rejects_disabled_auth() -> None:
    settings = replace(
        load_settings(),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="disabled",
        azure_cosmos_key="",
        azure_cosmos_auth_mode="managed_identity",
    )

    with pytest.raises(RuntimeError, match="AUTH_MODE=disabled"):
        validate_security_settings(settings)


def test_business_scope_requires_token_in_cloud() -> None:
    settings = replace(
        load_settings(),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="entra_id",
        entra_tenant_id="tenant",
        entra_client_id="client",
        entra_audience="api://client",
        azure_cosmos_key="",
        azure_cosmos_auth_mode="managed_identity",
    )
    dependency = require_scopes("decision:write")

    with pytest.raises(HTTPException) as error:
        asyncio.run(dependency(security_scopes=None, credentials=None, settings=settings))

    assert error.value.status_code == 401


def test_business_scope_rejects_token_without_required_scope(monkeypatch) -> None:
    settings = replace(
        load_settings(),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="entra_id",
        entra_tenant_id="tenant",
        entra_client_id="client",
        entra_audience="api://client",
        azure_cosmos_key="",
        azure_cosmos_auth_mode="managed_identity",
    )

    monkeypatch.setattr(
        "src.api.security.validate_entra_token",
        lambda token, settings: Principal("user", frozenset({"decision:read"}), {}),
    )
    dependency = require_scopes("decision:write")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    with pytest.raises(HTTPException) as error:
        asyncio.run(dependency(security_scopes=None, credentials=credentials, settings=settings))

    assert error.value.status_code == 403


def test_cloud_security_rejects_permanent_cosmos_key() -> None:
    settings = replace(
        load_settings(),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="entra_id",
        entra_tenant_id="tenant",
        entra_client_id="client",
        entra_audience="api://client",
        subject_key_salt="cloud-secret",
        azure_cosmos_key="permanent-key",
        azure_cosmos_auth_mode="managed_identity",
    )

    with pytest.raises(RuntimeError, match="Permanent AZURE_COSMOS_KEY"):
        validate_security_settings(settings)


def test_cloud_security_requires_cosmos_decision_repository() -> None:
    settings = replace(
        load_settings(),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="entra_id",
        entra_tenant_id="tenant",
        entra_client_id="client",
        entra_audience="api://client",
        subject_key_salt="cloud-secret",
        azure_cosmos_key="",
        azure_cosmos_auth_mode="managed_identity",
        decision_repository_mode="file",
    )

    with pytest.raises(RuntimeError, match="DECISION_REPOSITORY_MODE=cosmos"):
        validate_security_settings(settings)


def route_endpoint(app, path: str, method: str):
    return route_for(app, path, method).endpoint


def route_for(app, path: str, method: str):
    routes = []
    for item in app.routes:
        routes.extend(getattr(getattr(item, "original_router", None), "routes", [item]))

    for route in routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"Route not found: {method} {path}")
