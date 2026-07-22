from __future__ import annotations

import json
from uuid import UUID

import pandas as pd

from src.engine.likelihood import PurchaseLikelihoodService, train_likelihood_model
from src.engine.schemas import EngineRequest
from src.engine.service import DecisionService


def processed_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": [f"row_{index}" for index in range(18)],
            "recency": [1, 2, 3] * 6,
            "history_segment": ["1) Low", "2) Medium", "3) High"] * 6,
            "mens": [1, 0, 1] * 6,
            "womens": [0, 1, 1] * 6,
            "newbie": [1, 0, 0] * 6,
            "channel": ["Web", "Phone", "Multichannel"] * 6,
            "action": ["mens_email", "womens_email", "no_email"] * 6,
            "reward": [1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 0],
            "visit": [1, 0, 1] * 6,
            "spend": [10.0, 0.0, 0.0] * 6,
        }
    )


def test_train_likelihood_model_writes_expected_artifact(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    output_file = tmp_path / "purchase_likelihood_model.json"
    processed_dataframe().to_csv(input_file, index=False)

    model = train_likelihood_model(input_file=input_file, output_file=output_file, min_samples=2)

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert model.global_count == 18
    assert payload["version"] == "likelihood-v1"
    assert set(payload["action_rates"]) == {"mens_email", "womens_email", "no_email"}
    assert payload["context_rates"]


def test_purchase_likelihood_uses_context_then_action_fallback(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    output_file = tmp_path / "purchase_likelihood_model.json"
    processed_dataframe().to_csv(input_file, index=False)
    model = train_likelihood_model(input_file=input_file, output_file=output_file, min_samples=2)
    service = PurchaseLikelihoodService(model)

    contextual = service.estimate(
        EngineRequest(
            request_id="req_1",
            customer_context={"channel": "Web", "history_segment": "1) Low", "newbie": 1},
            eligible_offers=["mens_email"],
        )
    )
    fallback = service.estimate(
        EngineRequest(
            request_id="req_2",
            customer_context={"history_segment": "1) Low"},
            eligible_offers=["cashback_recurring_purchase"],
        )
    )

    assert contextual.estimates[0].fallback_level.startswith("context:")
    assert fallback.estimates[0].fallback_level == "action_rate"
    assert 0.0 <= fallback.estimates[0].purchase_likelihood <= 1.0


def test_purchase_likelihood_rejects_empty_eligible_offers(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    output_file = tmp_path / "purchase_likelihood_model.json"
    processed_dataframe().to_csv(input_file, index=False)
    model = train_likelihood_model(input_file=input_file, output_file=output_file)
    service = PurchaseLikelihoodService(model)

    try:
        service.estimate(
            EngineRequest(
                request_id="req_1",
                customer_context={"channel": "Web"},
                eligible_offers=[],
            )
        )
    except ValueError as error:
        assert "eligible_offers" in str(error)
    else:
        raise AssertionError("Expected eligible_offers validation error")


def test_decision_service_recommends_only_eligible_offer(tmp_path) -> None:
    input_file = tmp_path / "processed.csv"
    model_file = tmp_path / "purchase_likelihood_model.json"
    selected_policy_file = tmp_path / "selected_policy.json"
    processed_dataframe().to_csv(input_file, index=False)
    train_likelihood_model(input_file=input_file, output_file=model_file)
    selected_policy_file.write_text(
        json.dumps(
            {
                "schema_version": "selected_policy.v1",
                "artifact_status": "active",
                "policy": "thompson_sampling",
                "version": "offline-v1",
                "selection_rule": "test fixture",
                "metrics": {"rounds": 18},
            }
        ),
        encoding="utf-8",
    )
    service = DecisionService.from_files(model_file, selected_policy_file)

    response = service.decide(
        EngineRequest(
            request_id="req_1",
            customer_context={"channel": "Web", "history_segment": "1) Low", "newbie": 1},
            eligible_offers=["financial_education", "cashback_recurring_purchase"],
        )
    )

    assert response.offer_id in {"financial_education", "cashback_recurring_purchase"}
    assert response.policy == "likelihood_ranker"
    assert response.policy_version == "likelihood-v1"
    assert response.artifact_schema == "purchase_likelihood_model.v1"
    assert response.artifact_version == "likelihood-v1"
    assert len(response.artifact_checksum) == 64
    assert response.artifact_status == "active"
    assert response.decision_id.startswith("dec_")
    UUID(response.decision_id.removeprefix("dec_"))
    assert response.created_at
