from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

fastapi = pytest.importorskip("fastapi")

try:
    from fastapi.testclient import TestClient
except RuntimeError as error:
    TestClient = None
    TESTCLIENT_UNAVAILABLE = str(error)
else:
    TESTCLIENT_UNAVAILABLE = ""


requires_testclient = pytest.mark.skipif(
    TestClient is None,
    reason=TESTCLIENT_UNAVAILABLE or "TestClient dependency is unavailable",
)

import src.api.main as api_main
from src.api import dependencies
from src.api.schemas.decisions import DecisionRequest
from src.api.schemas.errors import ErrorResponse
from src.api.schemas.rewards import RewardRequest
from src.api.security import Principal, require_scopes, validate_security_settings
from src.core.config import load_settings
from src.engine.likelihood import train_likelihood_model
from src.engine.service import DecisionService
from src.storage.decision_repository import InMemoryDecisionRepository


def processed_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": [f"row_{index}" for index in range(9)],
            "recency": [1, 2, 3] * 3,
            "history_segment": ["1) Low", "2) Medium", "3) High"] * 3,
            "newbie": [1, 0, 0] * 3,
            "channel": ["Web", "Phone", "Multichannel"] * 3,
            "action": ["legacy_variant_a", "legacy_variant_b", "legacy_control"] * 3,
            "reward": [1, 0, 0, 1, 1, 0, 1, 0, 0],
            "visit": [1, 0, 1] * 3,
            "spend": [10.0, 0.0, 0.0] * 3,
        }
    )


def decision_test_components(tmp_path):
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
    app = api_main.create_app(service, repository)
    request = DecisionRequest(
        request_id="req_1",
        customer_context={"channel": "Web", "history_segment": "1) Low", "newbie": 1},
        eligible_offers=["cashback_recurring_purchase", "financial_education"],
    )
    return service, repository, app, request


def api_test_client(app):
    return TestClient(app, base_url="http://127.0.0.1")


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
        settings=load_settings(use_env_file=False),
    )
    repeated = route_endpoint(app, "/v1/decisions", "POST")(
        request,
        idempotency_key="idem-1",
        principal=principal,
        service=service,
        repository=repository,
        settings=load_settings(use_env_file=False),
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
    assert record.ttl == load_settings(use_env_file=False).decision_event_ttl_seconds


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
        settings=load_settings(use_env_file=False),
    )
    second = route_endpoint(app, "/v1/decisions", "POST")(
        request,
        idempotency_key=None,
        principal=principal,
        service=service,
        repository=repository,
        settings=load_settings(use_env_file=False),
    )

    assert first["decision_id"] != second["decision_id"]
    assert repository.event_count == 2


def test_reward_ingestion_is_idempotent_and_append_only(tmp_path) -> None:
    service, repository, app, request = decision_test_components(tmp_path)
    principal = Principal("user-1", frozenset({"decision:write", "reward:write"}), {})
    decision = route_endpoint(app, "/v1/decisions", "POST")(
        request,
        idempotency_key="idem-1",
        principal=principal,
        service=service,
        repository=repository,
        settings=load_settings(use_env_file=False),
    )
    reward_request = RewardRequest(
        decision_id=decision["decision_id"],
        event_id="evt_123",
        event_type="conversion",
        reward=1.0,
        occurred_at="2099-07-22T20:00:00Z",
    )

    reward = route_endpoint(app, "/v1/rewards", "POST")(
        reward_request,
        principal=principal,
        repository=repository,
        settings=load_settings(use_env_file=False),
    )
    repeated = route_endpoint(app, "/v1/rewards", "POST")(
        reward_request,
        principal=principal,
        repository=repository,
        settings=load_settings(use_env_file=False),
    )

    assert reward == repeated
    assert reward["accepted"] is True
    assert reward["decision_id"] == decision["decision_id"]
    assert len(repository.reward_records) == 1


def test_reward_rejects_orphan_decision(tmp_path) -> None:
    _, repository, app, _ = decision_test_components(tmp_path)
    principal = Principal("user-1", frozenset({"reward:write"}), {})
    reward_request = RewardRequest(
        decision_id="dec_missing",
        event_id="evt_123",
        event_type="conversion",
        reward=1.0,
        occurred_at="2099-07-22T20:00:00Z",
    )

    with pytest.raises(HTTPException) as error:
        route_endpoint(app, "/v1/rewards", "POST")(
            reward_request,
            principal=principal,
            repository=repository,
            settings=load_settings(use_env_file=False),
        )

    assert error.value.status_code == 400
    assert "decision_id" in error.value.detail["message"]


def test_reward_rejects_other_subject_decision(tmp_path) -> None:
    service, repository, app, request = decision_test_components(tmp_path)
    owner = Principal("user-1", frozenset({"decision:write"}), {})
    other = Principal("user-2", frozenset({"reward:write"}), {})
    decision = route_endpoint(app, "/v1/decisions", "POST")(
        request,
        idempotency_key="idem-1",
        principal=owner,
        service=service,
        repository=repository,
        settings=load_settings(use_env_file=False),
    )
    reward_request = RewardRequest(
        decision_id=decision["decision_id"],
        event_id="evt_123",
        event_type="conversion",
        reward=1.0,
        occurred_at="2099-07-22T20:00:00Z",
    )

    with pytest.raises(HTTPException) as error:
        route_endpoint(app, "/v1/rewards", "POST")(
            reward_request,
            principal=other,
            repository=repository,
            settings=load_settings(use_env_file=False),
        )

    assert error.value.status_code == 400


def test_reward_rejects_timestamp_before_decision(tmp_path) -> None:
    service, repository, app, request = decision_test_components(tmp_path)
    principal = Principal("user-1", frozenset({"decision:write", "reward:write"}), {})
    decision = route_endpoint(app, "/v1/decisions", "POST")(
        request,
        idempotency_key="idem-1",
        principal=principal,
        service=service,
        repository=repository,
        settings=load_settings(use_env_file=False),
    )
    reward_request = RewardRequest(
        decision_id=decision["decision_id"],
        event_id="evt_123",
        event_type="conversion",
        reward=1.0,
        occurred_at="2000-01-01T00:00:00Z",
    )

    with pytest.raises(HTTPException) as error:
        route_endpoint(app, "/v1/rewards", "POST")(
            reward_request,
            principal=principal,
            repository=repository,
            settings=load_settings(use_env_file=False),
        )

    assert error.value.status_code == 400
    assert "occurred_at" in error.value.detail["message"]


def test_reward_schema_rejects_invalid_reward_value() -> None:
    with pytest.raises(ValidationError) as error:
        RewardRequest(
            decision_id="dec_123",
            event_id="evt_123",
            event_type="conversion",
            reward=1.5,
            occurred_at="2099-07-22T20:00:00Z",
        )

    assert "less than or equal to 1" in str(error.value)


def test_api_startup_fails_when_artifact_is_missing(monkeypatch) -> None:
    def fail_from_directory(artifact_dir):
        raise FileNotFoundError("missing model artifact")

    monkeypatch.setattr(
        dependencies.DecisionService,
        "from_directory",
        staticmethod(fail_from_directory),
    )

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
                "cashback_recurring_purchase",
                "savings_goal",
                "financial_education",
                "account_upgrade",
                "installment_education",
                "credit_limit",
                "personal_loan",
                "cashback_investment",
                "savings_goal",
            ],
        )

    assert "at most 8 items" in str(error.value)


def test_api_routes_have_explicit_response_models() -> None:
    app = api_main.create_app()

    for path, method in [
        ("/livez", "GET"),
        ("/readyz", "GET"),
        ("/v1/policies/current", "GET"),
        ("/v1/likelihood-estimates", "POST"),
        ("/v1/purchase-likelihood", "POST"),
        ("/v1/decisions", "POST"),
        ("/v1/rewards", "POST"),
        ("/v2/policies/current", "GET"),
        ("/v2/likelihood-estimates", "POST"),
        ("/v2/decisions", "POST"),
        ("/v2/feedback", "POST"),
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
        ("/v1/rewards", "POST"): {"reward:write"},
        ("/v2/policies/current", "GET"): {"policy:read"},
        ("/v2/likelihood-estimates", "POST"): {"decision:read"},
        ("/v2/decisions", "POST"): {"decision:write"},
        ("/v2/feedback", "POST"): {"reward:write"},
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


@requires_testclient
def test_http_readiness_uses_loaded_service(tmp_path) -> None:
    _, _, app, _ = decision_test_components(tmp_path)

    with api_test_client(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "ecloe-engine"}
    assert response.headers["x-request-id"]
    assert response.headers["x-trace-id"]


@requires_testclient
def test_http_rejects_unknown_fields(tmp_path) -> None:
    _, _, app, _ = decision_test_components(tmp_path)
    payload = {
        "request_id": "req_1",
        "customer_context": {"channel": "Web", "zip_code": "12345"},
        "eligible_offers": ["cashback_recurring_purchase"],
        "unexpected": True,
    }

    with api_test_client(app) as client:
        response = client.post("/v1/decisions", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


@requires_testclient
def test_http_rate_limit_returns_standard_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    _, _, app, _ = decision_test_components(tmp_path)

    with api_test_client(app) as client:
        first = client.get("/livez")
        second = client.get("/livez")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {"code": "invalid_request", "message": "Rate limit exceeded."}


@requires_testclient
def test_http_decision_idempotency_and_log_redaction(caplog, tmp_path) -> None:
    _, repository, app, _ = decision_test_components(tmp_path)
    payload = {
        "request_id": "req_1",
        "customer_context": {"channel": "Web", "history_segment": "1) Low", "newbie": 1},
        "eligible_offers": ["cashback_recurring_purchase", "financial_education"],
    }

    with caplog.at_level(logging.INFO, logger="ecloe.api.access"), api_test_client(app) as client:
        first = client.post("/v1/decisions", json=payload, headers={"Idempotency-Key": "idem-1"})
        second = client.post(
            "/v1/decisions",
            json=payload,
            headers={"Idempotency-Key": "idem-1", "X-Request-Id": "traceable-request"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert repository.event_count == 1
    log_messages = "\n".join(record.message for record in caplog.records)
    assert "customer_context" not in log_messages
    assert "history_segment" not in log_messages
    assert "traceable-request" in log_messages
    assert first.json()["decision_id"] in log_messages
    assert first.json()["policy_version"] in log_messages


@requires_testclient
def test_http_reward_duplicate_returns_previous_response(tmp_path) -> None:
    _, repository, app, _ = decision_test_components(tmp_path)
    decision_payload = {
        "request_id": "req_1",
        "customer_context": {"channel": "Web", "history_segment": "1) Low", "newbie": 1},
        "eligible_offers": ["cashback_recurring_purchase", "financial_education"],
    }

    with api_test_client(app) as client:
        decision = client.post(
            "/v1/decisions",
            json=decision_payload,
            headers={"Idempotency-Key": "idem-1"},
        )
        reward_payload = {
            "decision_id": decision.json()["decision_id"],
            "event_id": "evt_123",
            "event_type": "conversion",
            "reward": 1.0,
            "occurred_at": "2099-07-22T20:00:00Z",
        }
        first = client.post("/v1/rewards", json=reward_payload)
        second = client.post("/v1/rewards", json=reward_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(repository.reward_records) == 1


@requires_testclient
def test_http_business_route_requires_token_in_cloud(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "cloud")
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("AUTH_MODE", "entra_id")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client")
    monkeypatch.setenv("ENTRA_AUDIENCE", "api://client")
    monkeypatch.setenv("SUBJECT_KEY_SALT", "cloud-secret")
    monkeypatch.setenv("AZURE_COSMOS_AUTH_MODE", "managed_identity")
    monkeypatch.setenv("DECISION_REPOSITORY_MODE", "cosmos")
    monkeypatch.setenv("ECLOE_PAY_SQL_AUTH_MODE", "managed_identity")
    monkeypatch.setattr("src.api.dependencies.validate_security_settings", lambda settings: None)
    _, _, app, _ = decision_test_components(tmp_path)

    with api_test_client(app) as client:
        response = client.post(
            "/v1/decisions",
            json={
                "request_id": "req_1",
                "customer_context": {"channel": "Web"},
                "eligible_offers": ["cashback_recurring_purchase"],
            },
        )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


@requires_testclient
def test_http_business_route_rejects_missing_scope(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "cloud")
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("AUTH_MODE", "entra_id")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client")
    monkeypatch.setenv("ENTRA_AUDIENCE", "api://client")
    monkeypatch.setenv("SUBJECT_KEY_SALT", "cloud-secret")
    monkeypatch.setenv("AZURE_COSMOS_AUTH_MODE", "managed_identity")
    monkeypatch.setenv("DECISION_REPOSITORY_MODE", "cosmos")
    monkeypatch.setenv("ECLOE_PAY_SQL_AUTH_MODE", "managed_identity")
    monkeypatch.setattr("src.api.dependencies.validate_security_settings", lambda settings: None)
    monkeypatch.setattr(
        "src.api.security.validate_entra_token",
        lambda token, settings: Principal("user", frozenset({"decision:read"}), {}),
    )
    _, _, app, _ = decision_test_components(tmp_path)

    with api_test_client(app) as client:
        response = client.post(
            "/v1/decisions",
            json={
                "request_id": "req_1",
                "customer_context": {"channel": "Web"},
                "eligible_offers": ["cashback_recurring_purchase"],
            },
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_openapi_contract_has_explicit_reward_route(tmp_path) -> None:
    _, _, app, _ = decision_test_components(tmp_path)
    contract = app.openapi()

    assert contract["paths"]["/v1/rewards"]["post"]["responses"]["200"]["description"]
    assert (
        contract["paths"]["/v1/decisions"]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        == "#/components/schemas/DecisionRequest"
    )


@requires_testclient
def test_corrupted_artifact_fails_startup(tmp_path, monkeypatch) -> None:
    model_file = tmp_path / "purchase_likelihood_model.json"
    policy_file = tmp_path / "selected_policy.json"
    original_from_files = DecisionService.from_files
    model_file.write_text("{bad json", encoding="utf-8")
    policy_file.write_text(
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
    monkeypatch.setattr(
        dependencies.DecisionService,
        "from_directory",
        staticmethod(lambda artifact_dir: original_from_files(model_file, policy_file)),
    )

    with pytest.raises(ValueError, match="not valid JSON"), api_test_client(api_main.create_app()):
        pass


def test_cloud_security_rejects_disabled_auth() -> None:
    settings = replace(
        load_settings(use_env_file=False),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="disabled",
        azure_cosmos_key="",
        azure_cosmos_auth_mode="managed_identity",
        artifact_source="azure_blob",
        azure_storage_account_url="https://example.blob.core.windows.net",
    )

    with pytest.raises(RuntimeError, match="AUTH_MODE=disabled"):
        validate_security_settings(settings)


def test_business_scope_requires_token_in_cloud() -> None:
    settings = replace(
        load_settings(use_env_file=False),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="entra_id",
        entra_tenant_id="tenant",
        entra_client_id="client",
        entra_audience="api://client",
        azure_cosmos_key="",
        azure_cosmos_auth_mode="managed_identity",
        artifact_source="azure_blob",
        azure_storage_account_url="https://example.blob.core.windows.net",
    )
    dependency = require_scopes("decision:write")

    with pytest.raises(HTTPException) as error:
        asyncio.run(dependency(security_scopes=None, credentials=None, settings=settings))

    assert error.value.status_code == 401


def test_business_scope_rejects_token_without_required_scope(monkeypatch) -> None:
    settings = replace(
        load_settings(use_env_file=False),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="entra_id",
        entra_tenant_id="tenant",
        entra_client_id="client",
        entra_audience="api://client",
        azure_cosmos_key="",
        azure_cosmos_auth_mode="managed_identity",
        artifact_source="azure_blob",
        azure_storage_account_url="https://example.blob.core.windows.net",
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
        load_settings(use_env_file=False),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="entra_id",
        entra_tenant_id="tenant",
        entra_client_id="client",
        entra_audience="api://client",
        subject_key_salt="cloud-secret",
        azure_cosmos_key="permanent-key",
        azure_cosmos_auth_mode="managed_identity",
        artifact_source="azure_blob",
        azure_storage_account_url="https://example.blob.core.windows.net",
    )

    with pytest.raises(RuntimeError, match="Permanent AZURE_COSMOS_KEY"):
        validate_security_settings(settings)


def test_cloud_security_requires_cosmos_decision_repository() -> None:
    settings = replace(
        load_settings(use_env_file=False),
        app_environment="cloud",
        api_host="0.0.0.0",
        auth_mode="entra_id",
        entra_tenant_id="tenant",
        entra_client_id="client",
        entra_audience="api://client",
        subject_key_salt="cloud-secret",
        azure_cosmos_key="",
        azure_cosmos_auth_mode="managed_identity",
        artifact_source="azure_blob",
        azure_storage_account_url="https://example.blob.core.windows.net",
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
