import re

from src.demo.app import create_app
from src.demo.ecloe_pay.app import CSRF_COOKIE_NAME
from src.demo.ecloe_pay.repositories import SHARED_DEMO_USER_EMAIL


def csrf_headers(client) -> dict[str, str]:
    cookie = client.get_cookie(CSRF_COOKIE_NAME)
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def authenticated_client(app=None):
    app = app or create_app()
    client = app.test_client()
    client.get("/pay/login")
    response = client.post(
        "/api/auth/login",
        json={"email": SHARED_DEMO_USER_EMAIL, "password": "change-this-demo-password"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200
    return client


def test_integrated_demo_market_catalog_is_public() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/market")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "ECloe Market" in body
    assert "Visitor browsing the public catalog" in body
    assert "Search synthetic products" in body
    assert "Synthetic daily deals" in body
    assert "Selected for this journey" in body
    assert "deterministic_baseline" in body


def test_integrated_demo_market_checkout_requires_shared_login() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/market/checkout")

    assert response.status_code == 302
    assert response.headers["Location"] == "/pay/login?lang=en-US"


def test_integrated_demo_market_renders_after_pay_login() -> None:
    app = create_app()
    client = authenticated_client(app)

    response = client.get("/market")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "ECloe Market" in body
    assert "No real money is processed" in body
    assert "/pay" in body


def test_integrated_demo_market_product_page_is_public() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/market/products/prd_demo_0001")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "ECloe Market" in body
    assert "Sign in for checkout" in body
    assert "Add to cart" in body


def test_integrated_demo_market_catalog_apis_are_local() -> None:
    app = create_app()
    client = app.test_client()

    categories = client.get("/api/market/categories")
    products = client.get("/api/market/products?q=Glow&sort=price_asc&limit=4")

    assert categories.status_code == 200
    assert products.status_code == 200
    assert len(categories.get_json()["categories"]) == 6
    payload = products.get_json()
    assert payload["products"]
    assert payload["limit"] == 4
    assert payload["products"][0]["is_demo"] is True
    assert isinstance(payload["products"][0]["price_cents"], int)
    assert payload["products"][0]["currency"] == "BRL"
    assert payload["products"][0]["stock_quantity"] >= 0
    assert "synthetic" in payload["products"][0]["synthetic_notice"].lower()


def test_integrated_demo_market_product_api_returns_detail() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/api/market/products/prd_demo_0001")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["product"]["product_id"] == "prd_demo_0001"
    assert payload["variants"]
    assert payload["current_prices"]
    assert payload["inventory_items"]
    assert isinstance(payload["current_prices"][0]["price_cents"], int)


def test_integrated_demo_market_public_filters_render() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/market?category_id=cat_beauty&q=Glow&sort=price_asc&page=1")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Apply" in body
    assert "Lowest price" in body


def test_integrated_demo_market_product_page_renders() -> None:
    app = create_app()
    client = authenticated_client(app)

    response = client.get("/market/products/prd_demo_0001")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "ECloe Market" in body
    assert "R$" in body
    assert "Demo variants" in body


def test_integrated_demo_market_cart_is_public_and_mutable_with_csrf() -> None:
    app = create_app()
    client = app.test_client()
    client.get("/market")

    add_response = client.post(
        "/api/market/cart/items",
        json={"product_id": "prd_demo_0001", "quantity": 2},
        headers=csrf_headers(client),
    )
    cart_page = client.get("/market/cart")

    assert add_response.status_code == 200
    payload = add_response.get_json()
    assert payload["cart"]["total_items"] == 2
    assert payload["cart"]["total_cents"] == 3980
    assert cart_page.status_code == 200
    assert "Shopping cart" in cart_page.get_data(as_text=True)
    assert "Glow balm 01" in cart_page.get_data(as_text=True)


def test_integrated_demo_market_cart_mutations_require_csrf() -> None:
    app = create_app()
    client = app.test_client()
    client.get("/market")

    response = client.post("/api/market/cart/items", json={"product_id": "prd_demo_0001"})

    assert response.status_code == 403
    assert "CSRF" in response.get_json()["error"]


def test_integrated_demo_market_persists_checkout_and_pending_order() -> None:
    app = create_app()
    client = authenticated_client(app)
    client.get("/market")
    add = client.post(
        "/api/market/cart/items",
        json={"product_id": "prd_demo_0001", "quantity": 2},
        headers=csrf_headers(client),
    )
    assert add.status_code == 200

    checkout_headers = {
        **csrf_headers(client),
        "Idempotency-Key": "checkout-market-test-001",
    }
    first_checkout = client.post("/api/market/checkouts", headers=checkout_headers)
    repeated_checkout = client.post("/api/market/checkouts", headers=checkout_headers)

    assert first_checkout.status_code == 200
    assert first_checkout.get_json() == repeated_checkout.get_json()
    checkout = first_checkout.get_json()["checkout"]
    assert checkout["status"] == "created"
    assert checkout["total_cents"] == 3980

    first_order = client.post(
        "/api/market/orders",
        json={"checkout_id": checkout["checkout_id"]},
        headers=csrf_headers(client),
    )
    repeated_order = client.post(
        "/api/market/orders",
        json={"checkout_id": checkout["checkout_id"]},
        headers=csrf_headers(client),
    )
    orders = client.get("/api/market/orders")

    assert first_order.status_code == 200
    assert first_order.get_json() == repeated_order.get_json()
    assert first_order.get_json()["order"]["status"] == "payment_pending"
    assert len(first_order.get_json()["order"]["items"]) == 1
    assert orders.status_code == 200
    assert len(orders.get_json()["orders"]) == 1


def test_integrated_demo_market_checkout_api_requires_login() -> None:
    app = create_app()
    client = app.test_client()
    client.get("/market")

    response = client.post(
        "/api/market/checkouts",
        headers={**csrf_headers(client), "Idempotency-Key": "checkout-anonymous"},
    )

    assert response.status_code == 401


def test_integrated_demo_market_records_only_feedback_from_presented_slate() -> None:
    app = create_app()
    client = app.test_client()
    page = client.get("/market")
    body = page.get_data(as_text=True)
    match = re.search(
        r'data-add-product="([^"]+)"\s+data-recommendation-decision="([^"]+)"\s+'
        r'data-recommendation-position="([^"]+)"',
        body,
    )
    assert match is not None
    product_id, decision_id, position = match.groups()

    accepted = client.post(
        "/api/market/recommendations/feedback",
        json={
            "decision_id": decision_id,
            "product_id": product_id,
            "position": int(position),
            "event_type": "add_to_cart",
            "event_id": "evt_market_feedback_test",
        },
        headers=csrf_headers(client),
    )
    rejected = client.post(
        "/api/market/recommendations/feedback",
        json={
            "decision_id": decision_id,
            "product_id": "prd_not_presented",
            "position": 1,
            "event_type": "add_to_cart",
        },
        headers=csrf_headers(client),
    )

    assert accepted.status_code == 200
    assert accepted.get_json()["terminal"] is False
    assert rejected.status_code == 400
    assert len(app.market_repository.recommendation_interactions) == 1
