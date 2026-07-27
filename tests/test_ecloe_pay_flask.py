from src.demo.ecloe_pay.app import DEMO_BUCKET_NAME, create_app


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


def test_pay_flask_session_exposes_demo_boundaries() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/api/session")

    assert response.status_code == 200
    body = response.get_json()
    assert body["security"]["user_creation_allowed"] is False
    assert body["security"]["real_money_processed"] is False
    assert body["security"]["bucket_name"] == DEMO_BUCKET_NAME
    assert body["security"]["postgres_schema"] == "ecloe_pay"


def test_pay_flask_requires_terms_before_interaction() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post("/api/benefit-interactions", json={"action": "accept"})

    assert response.status_code == 403
    assert response.get_json()["error"] == "Demo terms are required before recording interactions."


def test_pay_flask_accepts_terms_and_simulates_payment_once() -> None:
    app = create_app()
    client = app.test_client()

    terms_response = client.post("/api/terms", json={"accepted": True})
    payment_response = client.post(
        "/api/payment-orders/pay_order_demo_7841/simulate",
        json={"confirmation_code": "0426"},
    )
    duplicate_response = client.post(
        "/api/payment-orders/pay_order_demo_7841/simulate",
        json={"confirmation_code": "0426"},
    )

    assert terms_response.status_code == 200
    assert payment_response.status_code == 200
    body = payment_response.get_json()
    assert body["status"] == "verified"
    assert body["postgres_schema"] == "ecloe_pay"
    assert body["bucket_name"] == DEMO_BUCKET_NAME
    assert body["reward_event"]["event_type"] == "conversion"
    assert duplicate_response.status_code == 409
