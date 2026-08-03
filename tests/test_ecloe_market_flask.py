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


def test_integrated_demo_market_catalog_apis_are_local() -> None:
    app = create_app()
    client = app.test_client()

    categories = client.get("/api/market/categories")
    products = client.get("/api/market/products?q=Glow")

    assert categories.status_code == 200
    assert products.status_code == 200
    assert len(categories.get_json()["categories"]) == 6
    payload = products.get_json()
    assert payload["products"]
    assert payload["products"][0]["is_demo"] is True
    assert "synthetic" in payload["products"][0]["synthetic_notice"].lower()


def test_integrated_demo_market_product_page_renders() -> None:
    app = create_app()
    client = authenticated_client(app)

    response = client.get("/market/products/prd_demo_0001")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "ECloe Market" in body
    assert "R$" in body
