from __future__ import annotations

import re
import secrets
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, make_response, redirect, render_template, request

from src.demo.ecloe_pay.app import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from src.demo.ecloe_pay.identity import safe_return_to
from src.demo.shared.auth import current_user
from src.demo.shared.i18n import load_messages, resolve_locale, translate
from src.market.repositories import MarketRepository
from src.recommendation import Candidate, CandidateType, RecommendationRequest, Surface
from src.recommendation.privacy import neutralize_category

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
    effective_locale = locale if locale in ("pt-BR", "en-US") else "en-US"
    cookie_locale = "pt-BR" if effective_locale == "pt-BR" else "en-US"
    messages = load_messages(str(I18N_DIR), effective_locale)
    response = make_response(
        render_template(
            template_name,
            lang=effective_locale,
            locale=effective_locale,
            t=lambda key: translate(messages, key),
            **context,
        )
    )
    response.set_cookie(
        LOCALE_COOKIE_NAME,
        cookie_locale,
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
    session_key = request.cookies.get(MARKET_SESSION_COOKIE_NAME, "")
    if re.fullmatch(r"market_sess_[A-Za-z0-9_-]{32}", session_key):
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
        return_to = safe_return_to(request.full_path.rstrip("?"))
        login_query = urlencode(
            {
                "lang": resolve_locale(request, cookie_name=LOCALE_COOKIE_NAME),
                "return_to": return_to,
            }
        )
        return None, None, redirect(f"/pay/login?{login_query}")
    return user, user_id, None


def _optional_user():
    user, _ = current_user(current_app, request)
    return user


def _api_user_id():
    _, user_id = current_user(current_app, request)
    if user_id is None:
        return None, (jsonify({"error": "Authentication is required."}), 401)
    return user_id, None


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


def _price_band(price_cents: int) -> str:
    if price_cents < 5000:
        return "low"
    if price_cents < 15000:
        return "medium"
    return "high"


def _stock_band(quantity: int) -> str:
    if quantity <= 0:
        return "none"
    if quantity < 10:
        return "low"
    if quantity < 40:
        return "medium"
    return "high"


def _market_recommendations(
    repository: MarketRepository,
    session_key: str,
    category_id: str | None,
):
    products = repository.list_products(sort="featured", limit=50, offset=0)
    candidates = tuple(
        Candidate(
            candidate_id=product.product_id,
            candidate_type=CandidateType.product,
            available=product.active and product.stock_quantity > 0 and product.price_cents >= 0,
            category_id=neutralize_category(product.category_id),
            price_band=_price_band(product.price_cents),
            stock_band=_stock_band(product.stock_quantity),
            popularity_band="high" if product.rating >= 4.5 else "medium",
            priority=int(product.rating * 10),
        )
        for product in products
    )
    context: dict[str, object] = {"channel": "Web", "newbie": 1}
    if category_id:
        context["category_affinities"] = [neutralize_category(category_id)]
    decision = current_app.recommendation_service.decide(  # type: ignore[attr-defined]
        RecommendationRequest(
            request_id=f"req_market_{session_key[-12:]}",
            surface=Surface.market,
            decision_point="market_home",
            context=context,
            candidates=candidates,
            limit=6,
        )
    )
    decision_payload = asdict(decision)
    decision_payload["session_key"] = session_key
    current_app.recommendation_decisions[decision.decision_id] = decision_payload  # type: ignore[attr-defined]
    products_by_id = {product.product_id: product for product in products}
    return decision, [products_by_id[item.candidate_id] for item in decision.ranked_candidates]


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
    recommendation, recommended_products = _market_recommendations(
        repository,
        session_key,
        catalog_query["category_id"],  # type: ignore[arg-type]
    )
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
        recommendation=recommendation,
        recommended_products=recommended_products,
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
def market_checkout():
    user, _, login_response = _require_login()
    if login_response is not None:
        return login_response
    session_key = _market_session_key()
    cart = _repository().get_cart(session_key)
    if cart.empty:
        return redirect("/market/cart")
    response = _render_market_template(
        "market_checkout.html",
        user=user,
        cart=cart,
    )
    return _attach_market_session(response, session_key)


@market_blueprint.get("/market/orders")
def planned_market_orders():
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
        current_app.logger.warning("Invalid cart item payload", exc_info=error)
        return jsonify({"error": "Invalid request payload."}), 400
    response = jsonify({"cart": _cart_payload(cart)})
    return _attach_market_session(response, session_key)


@market_blueprint.post("/api/market/recommendations/feedback")
def api_recommendation_feedback():
    if not _csrf_valid():
        return _csrf_error()
    payload = request.get_json(silent=True) or {}
    decision_id = str(payload.get("decision_id", ""))
    product_id = str(payload.get("product_id", ""))
    event_type = str(payload.get("event_type", ""))
    try:
        position = int(payload.get("position", 0))
    except (TypeError, ValueError):
        position = 0
    session_key = _market_session_key()
    decision = current_app.recommendation_decisions.get(decision_id)  # type: ignore[attr-defined]
    ranked = decision.get("ranked_candidates", []) if decision else []
    valid = any(
        item.get("candidate_id") == product_id and int(item.get("rank", 0)) == position
        for item in ranked
    ) and decision.get("session_key") == session_key
    if not valid or event_type not in {"impression", "click", "add_to_cart"}:
        return jsonify({"error": "Recommendation feedback does not match the presented slate."}), 400
    event_id = str(payload.get("event_id") or f"evt_market_{uuid4()}")
    if len(event_id) > 128:
        return jsonify({"error": "event_id is too long."}), 400
    _repository().record_recommendation_interaction(
        event_id=event_id,
        session_key=session_key,
        decision_id=decision_id,
        product_id=product_id,
        position=position,
        event_type=event_type,
    )
    response = jsonify({"recorded": True, "event_id": event_id, "terminal": False})
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
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid cart item request."}), 400
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


@market_blueprint.post("/api/market/checkouts")
def api_start_checkout():
    if not _csrf_valid():
        return _csrf_error()
    user_id, auth_error = _api_user_id()
    if auth_error is not None:
        return auth_error
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key or len(idempotency_key) > 180:
        return jsonify({"error": "A valid Idempotency-Key header is required."}), 400
    session_key = _market_session_key()
    try:
        checkout = _repository().start_checkout(
            session_key=session_key,
            user_id=str(user_id),
            idempotency_key=idempotency_key,
        )
    except ValueError as error:
        current_app.logger.warning("Checkout start failed due to invalid request.", exc_info=error)
        return jsonify({"error": "Invalid checkout request."}), 400
    response = jsonify({"checkout": asdict(checkout)})
    return _attach_market_session(response, session_key)


@market_blueprint.post("/api/market/orders")
def api_create_order():
    if not _csrf_valid():
        return _csrf_error()
    user_id, auth_error = _api_user_id()
    if auth_error is not None:
        return auth_error
    payload = request.get_json(silent=True) or {}
    checkout_id = str(payload.get("checkout_id", "")).strip()
    if not checkout_id:
        return jsonify({"error": "checkout_id is required."}), 400
    try:
        order = _repository().create_order(checkout_id=checkout_id, user_id=str(user_id))
    except ValueError as error:
        current_app.logger.warning("Order creation failed due to invalid request.", exc_info=error)
        return jsonify({"error": "Invalid order request."}), 400
    return jsonify({"order": asdict(order)})


@market_blueprint.post("/api/market/orders/<order_id>/pay")
def api_pay_order(order_id: str):
    if not _csrf_valid():
        return _csrf_error()
    user_id, auth_error = _api_user_id()
    if auth_error is not None:
        return auth_error
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key or len(idempotency_key) > 180:
        return jsonify({"error": "A valid Idempotency-Key header is required."}), 400
    order = next(
        (item for item in _repository().list_orders(user_id=str(user_id)) if item.order_id == order_id),
        None,
    )
    if order is None:
        return jsonify({"error": "Synthetic ECloe Market order was not found."}), 404
    try:
        payment = current_app.pay_repository.pay_market_order(  # type: ignore[attr-defined]
            user_id=str(user_id),
            market_order_id=order.order_id,
            amount_cents=order.total_cents,
            currency=order.currency,
            idempotency_key=idempotency_key,
        )
        paid_order = _repository().mark_order_paid(
            order_id=order.order_id,
            user_id=str(user_id),
            payment_id=payment.payment_id,
            pay_payment_order_id=payment.payment_id,
            amount_cents=payment.amount_cents,
            currency=payment.currency,
        )
    except ValueError as error:
        current_app.logger.warning("Market order payment conflict for order_id=%s: %s", order_id, error)
        message = str(error)
        if message != "Insufficient ECloe Pay balance.":
            message = "Unable to process payment for this order."
        return jsonify({"error": message}), 409
    response = jsonify(
        {
            "payment": asdict(payment),
            "order": asdict(paid_order),
            "wallet": asdict(current_app.pay_repository.synthetic_account(str(user_id))),  # type: ignore[attr-defined]
        }
    )
    return _attach_market_session(response, _market_session_key())


@market_blueprint.get("/api/market/orders")
def api_list_orders():
    user_id, auth_error = _api_user_id()
    if auth_error is not None:
        return auth_error
    return jsonify(
        {"orders": [asdict(order) for order in _repository().list_orders(user_id=str(user_id))]}
    )


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
