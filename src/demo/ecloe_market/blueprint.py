from __future__ import annotations

import secrets
from dataclasses import asdict
from pathlib import Path

from flask import Blueprint, current_app, jsonify, make_response, redirect, render_template, request

from src.demo.ecloe_pay.app import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from src.demo.shared.auth import current_user
from src.demo.shared.i18n import load_messages, resolve_locale, translate
from src.market.repositories import MarketRepository

MARKET_DIR = Path(__file__).resolve().parent
I18N_DIR = MARKET_DIR / "i18n"
LOCALE_COOKIE_NAME = "ecloe_market_locale"
MARKET_SESSION_COOKIE_NAME = "ecloe_market_session"

market_blueprint = Blueprint(
    "ecloe_market",
    __name__,
    static_folder=str(MARKET_DIR / "assets"),
    static_url_path="/market/assets",
    template_folder=str(MARKET_DIR),
)


def _repository() -> MarketRepository:
    return current_app.market_repository  # type: ignore[attr-defined]


def _render_market_template(template_name: str, **context):
    locale = resolve_locale(request, cookie_name=LOCALE_COOKIE_NAME)
    messages = load_messages(str(I18N_DIR), locale)
    response = make_response(
        render_template(
            template_name,
            lang=locale,
            locale=locale,
            t=lambda key: translate(messages, key),
            **context,
        )
    )
    response.set_cookie(
        LOCALE_COOKIE_NAME,
        locale,
        httponly=False,
        secure=current_app.pay_settings.app_environment != "local",  # type: ignore[attr-defined]
        samesite="Lax",
        path="/",
        max_age=60 * 60 * 24 * 365,
    )
    return response


def _csrf_valid() -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_token = request.headers.get(CSRF_HEADER_NAME, "")
    return bool(cookie_token and header_token and secrets.compare_digest(cookie_token, header_token))


def _csrf_error():
    return jsonify({"error": "CSRF token is missing or invalid."}), 403


def _market_session_key() -> str:
    session_key = request.cookies.get(MARKET_SESSION_COOKIE_NAME)
    if isinstance(session_key, str) and session_key.startswith("market_sess_"):
        return session_key
    return f"market_sess_{secrets.token_urlsafe(24)}"


def _attach_market_session(response, session_key: str):
    response.set_cookie(
        MARKET_SESSION_COOKIE_NAME,
        session_key,
        httponly=True,
        secure=current_app.pay_settings.app_environment != "local",  # type: ignore[attr-defined]
        samesite="Lax",
        path="/",
        max_age=60 * 60 * 24 * 14,
    )
    return response


def _require_login():
    user, user_id = current_user(current_app, request)
    if user_id is None:
        return None, None, redirect(f"/pay/login?lang={resolve_locale(request, cookie_name=LOCALE_COOKIE_NAME)}")
    return user, user_id, None


def _optional_user():
    user, _ = current_user(current_app, request)
    return user


def _positive_int_arg(name: str, default: int, *, maximum: int | None = None) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    value = max(value, 1)
    return min(value, maximum) if maximum is not None else value


def _catalog_query() -> dict[str, object]:
    page = _positive_int_arg("page", 1)
    limit = _positive_int_arg("limit", 12, maximum=24)
    return {
        "category_id": request.args.get("category_id") or None,
        "query": request.args.get("q") or None,
        "sort": request.args.get("sort") or "featured",
        "page": page,
        "limit": limit,
        "offset": (page - 1) * limit,
    }


def _product_payload(product) -> dict[str, object]:
    return {
        **asdict(product),
        "synthetic_notice": "Synthetic ECloe Market demo product. No real purchase is processed.",
    }


def _product_detail_payload(detail) -> dict[str, object]:
    return {
        "product": _product_payload(detail.product),
        "variants": [asdict(variant) for variant in detail.variants],
        "current_prices": [asdict(price) for price in detail.current_prices],
        "inventory_items": [asdict(item) for item in detail.inventory_items],
    }


def _cart_payload(cart) -> dict[str, object]:
    return {
        **asdict(cart),
        "total_items": cart.total_items,
        "total_cents": cart.total_cents,
        "empty": cart.empty,
        "synthetic_notice": "Synthetic ECloe Market demo cart. Checkout requires shared ECloe login.",
    }


@market_blueprint.get("/market")
def market_home():
    repository = _repository()
    session_key = _market_session_key()
    cart = repository.get_cart(session_key)
    catalog_query = _catalog_query()
    products = repository.list_products(
        category_id=catalog_query["category_id"],  # type: ignore[arg-type]
        query=catalog_query["query"],  # type: ignore[arg-type]
        sort=str(catalog_query["sort"]),
        limit=int(catalog_query["limit"]),
        offset=int(catalog_query["offset"]),
    )
    categories = repository.list_categories()
    categories_by_id = {category.category_id: category for category in categories}
    response = _render_market_template(
        "market_index.html",
        user=_optional_user(),
        products=products,
        categories=categories,
        categories_by_id=categories_by_id,
        catalog_query=catalog_query,
        cart=cart,
        has_next_page=len(products) == int(catalog_query["limit"]),
    )
    return _attach_market_session(response, session_key)


@market_blueprint.get("/market/products/<product_id>")
def product_detail(product_id: str):
    repository = _repository()
    session_key = _market_session_key()
    detail = repository.get_product_detail(product_id)
    if detail is None:
        response = _render_market_template("market_not_found.html", user=_optional_user())
        return _attach_market_session(response, session_key), 404
    categories_by_id = {category.category_id: category for category in repository.list_categories()}
    cart = repository.get_cart(session_key)
    response = _render_market_template(
        "market_product.html",
        user=_optional_user(),
        detail=detail,
        product=detail.product,
        category=categories_by_id.get(detail.product.category_id),
        cart=cart,
    )
    return _attach_market_session(response, session_key)


@market_blueprint.get("/market/cart")
def market_cart():
    session_key = _market_session_key()
    cart = _repository().get_cart(session_key)
    response = _render_market_template("market_cart.html", user=_optional_user(), cart=cart)
    return _attach_market_session(response, session_key)


@market_blueprint.get("/market/checkout")
@market_blueprint.get("/market/orders")
def planned_market_page():
    user, _, login_response = _require_login()
    if login_response is not None:
        return login_response
    return _render_market_template("market_planned.html", user=user, path=request.path)


@market_blueprint.get("/demo/summary")
def demo_summary():
    user, _, login_response = _require_login()
    if login_response is not None:
        return login_response
    return _render_market_template("market_summary.html", user=user)


@market_blueprint.get("/api/market/cart")
def api_cart():
    session_key = _market_session_key()
    cart = _repository().get_cart(session_key)
    response = jsonify({"cart": _cart_payload(cart)})
    return _attach_market_session(response, session_key)


@market_blueprint.post("/api/market/cart/items")
def api_add_cart_item():
    if not _csrf_valid():
        return _csrf_error()
    payload = request.get_json(silent=True) or {}
    session_key = _market_session_key()
    try:
        cart = _repository().add_cart_item(
            session_key=session_key,
            product_id=str(payload.get("product_id", "")),
            variant_id=payload.get("variant_id"),
            quantity=int(payload.get("quantity", 1)),
        )
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    response = jsonify({"cart": _cart_payload(cart)})
    return _attach_market_session(response, session_key)


@market_blueprint.patch("/api/market/cart/items/<cart_item_id>")
def api_update_cart_item(cart_item_id: str):
    if not _csrf_valid():
        return _csrf_error()
    payload = request.get_json(silent=True) or {}
    session_key = _market_session_key()
    try:
        cart = _repository().update_cart_item(
            session_key=session_key,
            cart_item_id=cart_item_id,
            quantity=int(payload.get("quantity", 1)),
        )
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    response = jsonify({"cart": _cart_payload(cart)})
    return _attach_market_session(response, session_key)


@market_blueprint.delete("/api/market/cart/items/<cart_item_id>")
def api_remove_cart_item(cart_item_id: str):
    if not _csrf_valid():
        return _csrf_error()
    session_key = _market_session_key()
    cart = _repository().remove_cart_item(session_key=session_key, cart_item_id=cart_item_id)
    response = jsonify({"cart": _cart_payload(cart)})
    return _attach_market_session(response, session_key)


@market_blueprint.get("/api/market/categories")
def api_categories():
    return jsonify({"categories": [asdict(category) for category in _repository().list_categories()]})


@market_blueprint.get("/api/market/products")
def api_products():
    catalog_query = _catalog_query()
    products = _repository().list_products(
        category_id=catalog_query["category_id"],  # type: ignore[arg-type]
        query=catalog_query["query"],  # type: ignore[arg-type]
        sort=str(catalog_query["sort"]),
        limit=int(catalog_query["limit"]),
        offset=int(catalog_query["offset"]),
    )
    return jsonify(
        {
            "products": [_product_payload(product) for product in products],
            "page": catalog_query["page"],
            "limit": catalog_query["limit"],
        }
    )


@market_blueprint.get("/api/market/products/<product_id>")
def api_product(product_id: str):
    detail = _repository().get_product_detail(product_id)
    if detail is None:
        return jsonify({"error": "Synthetic ECloe Market product was not found."}), 404
    return jsonify(_product_detail_payload(detail))
