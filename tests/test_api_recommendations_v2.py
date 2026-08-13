from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import src.api.main as api_main
from src.recommendation import RecommendationService
from src.storage.decision_repository import InMemoryDecisionRepository


def client_and_repository() -> tuple[TestClient, InMemoryDecisionRepository]:
    repository = InMemoryDecisionRepository()
    app = api_main.create_app(
        decision_service=object(),  # type: ignore[arg-type]
        decision_repository=repository,
        recommendation_service=RecommendationService(),
    )
    return TestClient(app, base_url="http://127.0.0.1"), repository


def market_payload() -> dict[str, object]:
    return {
        "request_id": "req_market_v2",
        "surface": "market",
        "decision_point": "market_home",
        "customer_context": {
            "channel": "Web",
            "newbie": 1,
            "category_affinities": ["womens-shoes"],
        },
        "eligible_candidates": [
            {
                "candidate_id": "prd_available",
                "candidate_type": "product",
                "available": True,
                "category_id": "womens-shoes",
                "price_band": "medium",
                "stock_band": "high",
                "popularity_band": "high",
                "priority": 10,
            },
            {
                "candidate_id": "prd_no_stock",
                "candidate_type": "product",
                "available": True,
                "category_id": "beauty",
                "price_band": "low",
                "stock_band": "none",
            },
        ],
        "limit": 6,
    }


def test_v2_decision_filters_stock_neutralizes_categories_and_is_idempotent() -> None:
    client, repository = client_and_repository()
    payload = market_payload()

    first = client.post("/v2/decisions", json=payload, headers={"Idempotency-Key": "idem-v2"})
    second = client.post("/v2/decisions", json=payload, headers={"Idempotency-Key": "idem-v2"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["policy"] == "deterministic_baseline"
    assert [item["candidate_id"] for item in first.json()["ranked_candidates"]] == [
        "prd_available"
    ]
    assert repository.event_count == 1
    assert repository.records[0].minimized_context["category_affinities"] == ["apparel"]


def test_v2_idempotency_key_rejects_a_different_request() -> None:
    client, _ = client_and_repository()
    payload = market_payload()
    assert client.post(
        "/v2/decisions", json=payload, headers={"Idempotency-Key": "idem-v2"}
    ).status_code == 200
    payload["request_id"] = "req_changed"

    response = client.post(
        "/v2/decisions", json=payload, headers={"Idempotency-Key": "idem-v2"}
    )

    assert response.status_code == 400
    assert "different request" in response.text


def test_v2_rejects_blocked_and_arbitrary_context_fields() -> None:
    client, _ = client_and_repository()
    for field in ("sex", "gender", "balance", "raw_navigation"):
        payload = market_payload()
        payload["customer_context"] = {"channel": "Web", field: "blocked"}
        response = client.post("/v2/decisions", json=payload)
        assert response.status_code == 422


def test_v2_pay_selects_exactly_one_eligible_benefit() -> None:
    client, _ = client_and_repository()
    response = client.post(
        "/v2/decisions",
        json={
            "request_id": "req_pay_v2",
            "surface": "pay",
            "decision_point": "wallet_home",
            "customer_context": {
                "channel": "Web",
                "wallet_engagement_band": "medium",
                "benefit_response_band": "unknown",
                "savings_goal_active": True,
            },
            "eligible_candidates": [
                {
                    "candidate_id": "benefit_a",
                    "candidate_type": "benefit",
                    "benefit_type": "cashback",
                    "priority": 20,
                },
                {
                    "candidate_id": "benefit_b",
                    "candidate_type": "benefit",
                    "benefit_type": "education",
                    "priority": 10,
                },
            ],
            "limit": 1,
        },
    )

    assert response.status_code == 200
    assert len(response.json()["ranked_candidates"]) == 1
    assert response.json()["ranked_candidates"][0]["candidate_id"] == "benefit_a"


def test_v2_feedback_maps_verified_terminal_reward_and_is_idempotent() -> None:
    client, repository = client_and_repository()
    decision = client.post("/v2/decisions", json=market_payload()).json()
    occurred_at = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    feedback = {
        "decision_id": decision["decision_id"],
        "event_id": "evt_purchase_1",
        "candidate_id": "prd_available",
        "position": 1,
        "event_type": "purchase",
        "occurred_at": occurred_at,
    }

    first = client.post("/v2/feedback", json=feedback)
    second = client.post("/v2/feedback", json=feedback)

    assert first.status_code == 200
    assert first.json()["reward"] == 1.0
    assert first.json()["terminal"] is True
    assert second.json() == first.json()
    assert len(repository.reward_records) == 1


def test_v2_feedback_rejects_candidate_outside_presented_slate() -> None:
    client, _ = client_and_repository()
    decision = client.post("/v2/decisions", json=market_payload()).json()

    response = client.post(
        "/v2/feedback",
        json={
            "decision_id": decision["decision_id"],
            "event_id": "evt_invalid_candidate",
            "candidate_id": "prd_not_presented",
            "position": 1,
            "event_type": "purchase",
            "occurred_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        },
    )

    assert response.status_code == 400
    assert "presented" in response.text


def test_v2_policy_endpoint_reports_shadow_challengers() -> None:
    client, _ = client_and_repository()

    response = client.get("/v2/policies/current?surface=market")

    assert response.status_code == 200
    assert response.json()["policy"] == "deterministic_baseline"
    assert response.json()["challenger_mode"] == "shadow"
    assert "thompson_sampling" in response.json()["challengers"]
