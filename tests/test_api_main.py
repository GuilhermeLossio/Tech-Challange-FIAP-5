from __future__ import annotations

import asyncio
import json

import pandas as pd
import pytest
from pydantic import ValidationError

fastapi = pytest.importorskip("fastapi")

import src.api.main as api_main  # noqa: E402
from src.engine.likelihood import train_likelihood_model  # noqa: E402
from src.engine.service import DecisionService  # noqa: E402


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
    endpoint = route_endpoint(app, "/health", "GET")

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

    app = api_main.create_app(service)
    payload = {
        "request_id": "req_1",
        "customer_context": {"channel": "Web", "history_segment": "1) Low", "newbie": 1},
        "eligible_offers": ["cashback_recurring_purchase", "financial_education"],
    }
    request = api_main.DecisionRequest(**payload)

    likelihood = route_endpoint(app, "/v1/purchase-likelihood", "POST")(request)
    decision = route_endpoint(app, "/v1/decisions", "POST")(request)
    policy = route_endpoint(app, "/v1/policy", "GET")()

    assert len(likelihood["estimates"]) == 2
    assert decision["offer_id"] in payload["eligible_offers"]
    assert decision["policy"] == "likelihood_ranker"
    assert decision["policy_version"] == model.version
    assert decision["artifact_version"] == model.version
    assert len(decision["artifact_checksum"]) == 64
    assert policy["policy"] == "likelihood_ranker"
    assert policy["artifact_checksum"] == decision["artifact_checksum"]
    assert policy["promoted_offline_policy"]["policy"] == "thompson_sampling"


def test_api_startup_fails_when_artifact_is_missing(monkeypatch) -> None:
    def fail_from_files():
        raise FileNotFoundError("missing model artifact")

    monkeypatch.setattr(api_main.DecisionService, "from_files", staticmethod(fail_from_files))

    async def run_lifespan() -> None:
        app = api_main.create_app()
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(FileNotFoundError, match="missing model artifact"):
        asyncio.run(run_lifespan())


def test_api_schema_rejects_unknown_context_fields() -> None:
    with pytest.raises(ValidationError) as error:
        api_main.DecisionRequest(
            request_id="req_1",
            customer_context={"channel": "Web", "zip_code": "12345"},
            eligible_offers=["cashback_recurring_purchase"],
        )

    assert "Extra inputs are not permitted" in str(error.value)


def test_api_schema_rejects_duplicate_offers() -> None:
    with pytest.raises(ValidationError) as error:
        api_main.DecisionRequest(
            request_id="req_1",
            customer_context={"channel": "Web"},
            eligible_offers=["cashback_recurring_purchase", "cashback_recurring_purchase"],
        )

    assert "duplicate offers" in str(error.value)


def test_api_schema_rejects_oversized_request() -> None:
    with pytest.raises(ValidationError) as error:
        api_main.DecisionRequest(
            request_id="r" * 65,
            customer_context={"channel": "Web"},
            eligible_offers=["cashback_recurring_purchase"],
        )

    assert "at most 64 characters" in str(error.value)


def test_api_schema_rejects_too_many_offers() -> None:
    with pytest.raises(ValidationError) as error:
        api_main.DecisionRequest(
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
        ("/health", "GET"),
        ("/v1/policy", "GET"),
        ("/v1/purchase-likelihood", "POST"),
        ("/v1/decisions", "POST"),
    ]:
        route = route_for(app, path, method)
        assert getattr(route, "response_model", None) is not None
        assert route.responses[422]["model"] is api_main.ErrorResponse


def route_endpoint(app, path: str, method: str):
    return route_for(app, path, method).endpoint


def route_for(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"Route not found: {method} {path}")
