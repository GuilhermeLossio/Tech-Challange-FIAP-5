from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import Blueprint, current_app, jsonify, make_response, redirect, render_template, request

from src.demo.shared.auth import current_user
from src.demo.shared.i18n import load_messages, resolve_locale, translate
from src.market.repositories import MarketRepository

MARKET_DIR = Path(__file__).resolve().parent
I18N_DIR = MARKET_DIR / "i18n"
LOCALE_COOKIE_NAME = "ecloe_market_locale"

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


def _require_login():
    user, user_id = current_user(current_app, request)
    if user_id is None:
        return None, None, redirect(f"/pay/login?lang={resolve_locale(request, cookie_name=LOCALE_COOKIE_NAME)}")
    return user, user_id, None


def _optional_user():
    user, _ = current_user(current_app, request)
    return user


def _product_payload(product) -> dict[str, object]:
    return {
        **asdict(product),
        "synthetic_notice": "Synthetic ECloe Market demo product. No real purchase is processed.",
    }


@market_blueprint.get("/market")
def market_home():
    repository = _repository()
    products = repository.list_products()[:12]
    categories = repository.list_categories()
    return _render_market_template(
        "market_index.html",
        user=_optional_user(),
        products=products,
        categories=categories,
    )


@market_blueprint.get("/market/products/<product_id>")
def product_detail(product_id: str):
    product = _repository().get_product(product_id)
    if product is None:
        return _render_market_template("market_not_found.html", user=_optional_user()), 404
    return _render_market_template("market_product.html", user=_optional_user(), product=product)


@market_blueprint.get("/market/cart")
def market_cart():
    return _render_market_template("market_planned.html", user=_optional_user(), path=request.path)


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


@market_blueprint.get("/api/market/categories")
def api_categories():
    return jsonify({"categories": [asdict(category) for category in _repository().list_categories()]})


@market_blueprint.get("/api/market/products")
def api_products():
    products = _repository().list_products(
        category_id=request.args.get("category_id"),
        query=request.args.get("q"),
    )
    return jsonify({"products": [_product_payload(product) for product in products]})


@market_blueprint.get("/api/market/products/<product_id>")
def api_product(product_id: str):
    product = _repository().get_product(product_id)
    if product is None:
        return jsonify({"error": "Synthetic ECloe Market product was not found."}), 404
    return jsonify({"product": _product_payload(product)})
