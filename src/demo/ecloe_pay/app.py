from __future__ import annotations

import hmac
import ipaddress
import logging
import os
import secrets
import time
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlencode

from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from src.core.config import Settings, load_settings
from src.demo.ecloe_pay.i18n import (
    LOCALE_COOKIE_NAME,
    load_messages,
    resolve_locale,
    translate,
)
from src.demo.ecloe_pay.identity import EntraExternalIdentity, OAuthClient, safe_return_to
from src.demo.ecloe_pay.repositories import (
    PayRepository,
    SignupEmailAlreadyExists,
    SignupIpLimitExceeded,
    create_pay_repository,
)
from src.recommendation import (
    Candidate,
    CandidateType,
    RecommendationRequest,
    RecommendationService,
    Surface,
)

DEMO_DIR = Path(__file__).resolve().parent
SHARED_DEMO_DIR = DEMO_DIR.parent / "shared"
AUTH_COOKIE_NAME = "ecloe_pay_session"
CSRF_COOKIE_NAME = "ecloe_pay_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
OIDC_FLOW_COOKIE_NAME = "ecloe_oidc_flow"
LOGIN_RATE_LIMIT_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 300
LOGGER = logging.getLogger(__name__)
PAY_BENEFITS = {
    "cashback_recurring_purchase": (
        "Cashback for recurring purchases",
        "Earn cashback on your recurring purchases.",
    ),
    "savings_goal": (
        "Savings goal boost",
        "Keep progress visible with a savings-goal benefit.",
    ),
    "financial_education": (
        "Financial education",
        "Open a short learning path selected for this wallet moment.",
    ),
}


def _cookie_secure(settings: Settings) -> bool:
    return settings.app_environment != "local"


def _set_auth_cookie(response, token: str, settings: Settings) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        httponly=True,
        secure=_cookie_secure(settings),
        samesite="Lax",
        path="/",
        max_age=settings.ecloe_pay_session_ttl_seconds,
    )


def _clear_auth_cookie(response, settings: Settings) -> None:
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        secure=_cookie_secure(settings),
        samesite="Lax",
        path="/",
    )


def _set_csrf_cookie(response, settings: Settings) -> str:
    token = secrets.token_hex(32)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        httponly=False,
        secure=_cookie_secure(settings),
        samesite="Lax",
        path="/",
        max_age=settings.ecloe_pay_session_ttl_seconds,
    )
    return token


def _csrf_valid() -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_token = request.headers.get(CSRF_HEADER_NAME, "")
    return bool(cookie_token and header_token) and hmac.compare_digest(cookie_token, header_token)


def _csrf_error():
    response = jsonify({"error": "Invalid ECloe Pay request token."})
    response.status_code = 403
    return response


def _auth_json(payload: dict[str, object], status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def _localized_login_url(locale: str, return_to: str | None = None) -> str:
    query = {"lang": locale}
    if return_to and return_to != "/pay":
        query["return_to"] = return_to
    return f"/pay/login?{urlencode(query)}"


def _redirect_to_safe_return(value: str | None):
    """Map validated local return paths to Flask routes without redirecting to raw input."""
    target = safe_return_to(value)
    if target == "/":
        return redirect("/")
    if target == "/market":
        return redirect("/market")
    if target == "/market/orders":
        return redirect("/market/orders")
    if target == "/demo/summary":
        return redirect("/demo/summary")
    return redirect("/pay")


def _render_demo_template(template_name: str, settings: Settings, **context):
    locale = resolve_locale(request)
    messages = load_messages(locale)
    response = make_response(
        render_template(
            template_name,
            locale=locale,
            lang=locale,
            t=lambda key: translate(messages, key),
            web_auth_mode=settings.ecloe_web_auth_mode,
            **context,
        ),
    )
    response.set_cookie(
        LOCALE_COOKIE_NAME,
        locale,
        httponly=False,
        secure=_cookie_secure(settings),
        samesite="Lax",
        path="/",
        max_age=60 * 60 * 24 * 365,
    )
    return response


def _rate_limit_key(email: str) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded.split(",", 1)[0].strip() or request.remote_addr or "unknown"
    return f"{ip_address}:{email}"


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    candidate = forwarded.split(",", 1)[0].strip() or request.remote_addr or "unknown"
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return "unknown"


def _signup_ip_hash(settings: Settings) -> str:
    return hmac.new(
        settings.subject_key_salt.encode("utf-8"),
        f"signup-ip\x00{_client_ip()}".encode(),
        "sha256",
    ).hexdigest()


def _signup_ip_allowlisted(settings: Settings) -> bool:
    client_ip = _client_ip()
    normalized_allowlist = set()
    for value in settings.ecloe_signup_admin_ip_allowlist:
        try:
            normalized_allowlist.add(str(ipaddress.ip_address(value)))
        except ValueError:
            continue
    return client_ip in normalized_allowlist


def _login_rate_limited(app: Flask, email: str) -> bool:
    now = time.monotonic()
    attempts: dict[str, list[float]] = app.pay_login_attempts  # type: ignore[attr-defined]
    key = _rate_limit_key(email)
    recent = [stamp for stamp in attempts.get(key, []) if now - stamp < LOGIN_RATE_LIMIT_WINDOW_SECONDS]
    if len(recent) >= LOGIN_RATE_LIMIT_ATTEMPTS:
        attempts[key] = recent
        return True
    recent.append(now)
    attempts[key] = recent
    return False


def _clear_login_attempts(app: Flask, email: str) -> None:
    attempts: dict[str, list[float]] = app.pay_login_attempts  # type: ignore[attr-defined]
    attempts.pop(_rate_limit_key(email), None)


def _current_user(app: Flask) -> tuple[dict[str, object] | None, str | None]:
    repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
    auth_session_id = request.cookies.get(AUTH_COOKIE_NAME)
    if isinstance(auth_session_id, str):
        auth_session = repository.get_auth_session(auth_session_id)
        if auth_session is not None:
            user = repository.get_user(auth_session.user_id)
            if user is not None:
                return asdict(user), auth_session.user_id
    return None, None


def _session_or_error(app: Flask):
    repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
    _, user_id = _current_user(app)
    if user_id is None:
        return None, jsonify({"error": "ECloe Pay login is required."}), 401
    demo_session = repository.get_or_create_demo_session(user_id)
    if not demo_session.selected_decision_id:
        demo_session = _assign_pay_recommendation(app, repository, demo_session)
    return demo_session, None, None


def _assign_pay_recommendation(app: Flask, repository: PayRepository, demo_session):
    wallet = repository.wallet_snapshot(demo_session.session_id)
    service: RecommendationService = app.recommendation_service  # type: ignore[attr-defined]
    decision = service.decide(
        RecommendationRequest(
            request_id=f"req_pay_{demo_session.session_id}",
            surface=Surface.pay,
            decision_point="wallet_benefit",
            context={
                "channel": "Web",
                "newbie": 0,
                "wallet_engagement_band": "medium",
                "benefit_response_band": "unknown",
                "savings_goal_active": wallet.savings_goal_percent > 0,
            },
            candidates=(
                Candidate(
                    "cashback_recurring_purchase",
                    CandidateType.benefit,
                    priority=30,
                    benefit_type="cashback",
                ),
                Candidate(
                    "savings_goal",
                    CandidateType.benefit,
                    priority=20,
                    benefit_type="savings",
                ),
                Candidate(
                    "financial_education",
                    CandidateType.benefit,
                    priority=10,
                    benefit_type="education",
                ),
            ),
            limit=1,
        )
    )
    selected = decision.ranked_candidates[0]
    app.recommendation_decisions[decision.decision_id] = asdict(decision)  # type: ignore[attr-defined]
    return repository.set_recommendation(
        demo_session.session_id,
        decision.decision_id,
        selected.candidate_id,
    )


def create_app(
    settings: Settings | None = None,
    repository: PayRepository | None = None,
    recommendation_service: RecommendationService | None = None,
    identity_client: OAuthClient | None = None,
) -> Flask:
    settings = settings or load_settings(use_env_file=False)
    app = Flask(
        __name__,
        static_folder=str(DEMO_DIR),
        static_url_path="",
        template_folder=str(DEMO_DIR),
    )
    app.config["JSON_SORT_KEYS"] = False
    if settings.app_environment in {"cloud", "prod", "production", "azure"}:
        if settings.ecloe_web_auth_mode not in {"entra_external", "local_signup"}:
            raise ValueError(
                "Cloud demo web must use ECLOE_WEB_AUTH_MODE=entra_external or local_signup."
            )
        if settings.ecloe_pay_database_mode != "azure_sql" or settings.ecloe_market_database_mode != "azure_sql":
            raise ValueError("Cloud demo web must persist Pay and Market state in Azure SQL.")
    if settings.app_environment in {"cloud", "prod", "production", "azure"}:
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=1, x_proto=1, x_host=1
        )
    app.secret_key = settings.subject_key_salt
    app.pay_settings = settings  # type: ignore[attr-defined]
    app.pay_repository = repository or create_pay_repository(settings)  # type: ignore[attr-defined]
    app.pay_login_attempts = {}  # type: ignore[attr-defined]
    app.recommendation_service = (  # type: ignore[attr-defined]
        recommendation_service or RecommendationService.from_settings(settings)
    )
    app.recommendation_decisions = {}  # type: ignore[attr-defined]
    app.external_identity = (  # type: ignore[attr-defined]
        EntraExternalIdentity(settings, identity_client)
        if settings.ecloe_web_auth_mode == "entra_external"
        else None
    )

    @app.after_request
    def harden_auth_responses(response):
        if request.path.startswith("/api/auth/"):
            response.headers["Cache-Control"] = "no-store"
        if request.method == "GET" and request.path in {
            "/pay/login",
            "/pay/register",
            "/pay",
            "/market",
            "/market/cart",
            "/market/checkout",
            "/market/orders",
            "/demo/summary",
        }:
            _set_csrf_cookie(response, settings)
        if request.method == "GET" and request.path.startswith("/market/products/"):
            _set_csrf_cookie(response, settings)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        if _cookie_secure(settings):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.get("/")
    def landing():
        return _render_demo_template("landing.html", settings)

    @app.get("/healthz")
    def healthz():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        if not repository.health_check():
            return jsonify({"status": "unhealthy"}), 503
        return jsonify({"status": "ok"})

    @app.get("/shared/<path:filename>")
    def shared_static(filename: str):
        return send_from_directory(SHARED_DEMO_DIR, filename)

    @app.get("/pay")
    def pay():
        locale = resolve_locale(request)
        user, _ = _current_user(app)
        if user is None:
            return redirect(_localized_login_url(locale))
        return _render_demo_template("index.html", settings)

    @app.get("/pay/login")
    def login_page():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        user, _ = _current_user(app)
        return_to = safe_return_to(request.args.get("return_to"))
        if user is not None and settings.ecloe_web_auth_mode in {"entra_external", "local_signup"}:
            return _redirect_to_safe_return(return_to)
        if settings.ecloe_web_auth_mode in {"local", "local_signup"}:
            auth_session_id = request.cookies.get(AUTH_COOKIE_NAME)
            if isinstance(auth_session_id, str):
                repository.revoke_auth_session(auth_session_id)
        external_login_url = "/auth/login?" + urlencode(
            {"return_to": return_to}
        )
        external_signup_url = "/auth/signup?" + urlencode(
            {"return_to": return_to}
        )
        response = _render_demo_template(
            "login.html",
            settings,
            return_to=return_to,
            external_login_url=external_login_url,
            external_signup_url=external_signup_url,
        )
        if settings.ecloe_web_auth_mode in {"local", "local_signup"}:
            _clear_auth_cookie(response, settings)
        return response

    @app.get("/auth/login")
    def external_login():
        return _begin_external_auth("login")

    @app.get("/auth/signup")
    def external_signup():
        return _begin_external_auth("signup")

    @app.get("/pay/register")
    def register_page():
        if settings.ecloe_web_auth_mode == "local_signup":
            user, _ = _current_user(app)
            return_to = safe_return_to(request.args.get("return_to"))
            if user is not None:
                return _redirect_to_safe_return(return_to)
            return _render_demo_template("register.html", settings, return_to=return_to)
        if settings.ecloe_web_auth_mode != "entra_external":
            return redirect(
                _localized_login_url(
                    resolve_locale(request),
                    safe_return_to(request.args.get("return_to")),
                )
            )
        return redirect("/auth/signup?" + urlencode({"return_to": safe_return_to(request.args.get("return_to"))}))

    def _begin_external_auth(intent: str):
        if settings.ecloe_web_auth_mode != "entra_external":
            return _auth_json({"error": "External authentication is not enabled."}, 404)
        flow_id = secrets.token_urlsafe(32)
        identity: EntraExternalIdentity = app.external_identity  # type: ignore[attr-defined]
        auth_uri = identity.begin(
            app.pay_repository,  # type: ignore[attr-defined]
            flow_id,
            safe_return_to(request.args.get("return_to")),
            intent=intent,
        )
        response = redirect(auth_uri)
        response.set_cookie(
            OIDC_FLOW_COOKIE_NAME,
            flow_id,
            httponly=True,
            secure=_cookie_secure(settings),
            samesite="Lax",
            path="/auth/callback",
            max_age=settings.ecloe_web_oidc_flow_ttl_seconds,
        )
        return response

    @app.get("/auth/callback")
    def external_callback():
        if settings.ecloe_web_auth_mode != "entra_external":
            return _auth_json({"error": "External authentication is not enabled."}, 404)
        flow_id = request.cookies.get(OIDC_FLOW_COOKIE_NAME, "")
        identity: EntraExternalIdentity = app.external_identity  # type: ignore[attr-defined]
        completed = identity.complete(app.pay_repository, flow_id, request.args.to_dict())  # type: ignore[attr-defined]
        if completed is None:
            app.pay_repository.record_audit_event(None, "login", "rejected")  # type: ignore[attr-defined]
            response = _auth_json({"error": "External authentication could not be completed."}, 401)
            response.delete_cookie(OIDC_FLOW_COOKIE_NAME, path="/auth/callback")
            return response
        external, return_to = completed
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        try:
            user = repository.provision_external_user(
                external.issuer,
                external.subject_key,
                signup_ip_hash=_signup_ip_hash(settings),
                allow_ip_reuse=_signup_ip_allowlisted(settings),
            )
        except SignupIpLimitExceeded:
            response = _auth_json(
                {"error": "This IP address has already created an ECloe account."},
                403,
            )
            response.delete_cookie(OIDC_FLOW_COOKIE_NAME, path="/auth/callback")
            return response
        if user is None:
            repository.record_audit_event(None, "login", "disabled")
            response = _auth_json({"error": "This account is not active."}, 403)
            response.delete_cookie(OIDC_FLOW_COOKIE_NAME, path="/auth/callback")
            return response
        previous_token = request.cookies.get(AUTH_COOKIE_NAME)
        if previous_token:
            repository.revoke_auth_session(previous_token)
        auth_session = repository.create_auth_session(user.user_id)
        repository.get_or_create_demo_session(user.user_id)
        repository.record_audit_event(user.user_id, "login", "success")
        response = _redirect_to_safe_return(return_to)
        _set_auth_cookie(response, auth_session.auth_session_id, settings)
        _set_csrf_cookie(response, settings)
        response.delete_cookie(OIDC_FLOW_COOKIE_NAME, path="/auth/callback")
        return response

    @app.post("/api/auth/login")
    def login():
        if settings.ecloe_web_auth_mode not in {"local", "local_signup"}:
            return _auth_json({"error": "Local credentials are disabled."}, 404)
        if not _csrf_valid():
            return _csrf_error()
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        if _login_rate_limited(app, email):
            LOGGER.info("ecloe_pay_login result=rate_limited")
            return _auth_json({"error": "Too many login attempts. Try again later."}, 429)
        user = repository.authenticate(email, password)
        if user is None:
            LOGGER.info("ecloe_pay_login result=invalid")
            return _auth_json({"error": "Invalid ECloe Pay demo credentials."}, 401)
        auth_session = repository.create_auth_session(user.user_id)
        repository.get_or_create_demo_session(user.user_id)
        _clear_login_attempts(app, email)
        response = _auth_json({"authenticated": True, "user": asdict(user)})
        _set_auth_cookie(response, auth_session.auth_session_id, settings)
        _set_csrf_cookie(response, settings)
        LOGGER.info("ecloe_pay_login user_id=%s result=success", user.user_id)
        return response

    @app.post("/api/auth/register")
    def register():
        if settings.ecloe_web_auth_mode != "local_signup":
            return _auth_json({"error": "Local signup is disabled."}, 404)
        if not _csrf_valid():
            return _csrf_error()
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        password_confirm = str(payload.get("password_confirm", ""))
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            return _auth_json({"error": "Informe um e-mail valido."}, 400)
        if len(password) < 8:
            return _auth_json({"error": "A senha deve ter pelo menos 8 caracteres."}, 400)
        if password != password_confirm:
            return _auth_json({"error": "A confirmacao de senha nao confere."}, 400)
        if _login_rate_limited(app, email):
            LOGGER.info("ecloe_pay_register result=rate_limited")
            return _auth_json({"error": "Too many registration attempts. Try again later."}, 429)
        try:
            user = repository.register_local_user(
                email,
                generate_password_hash(password),
                signup_ip_hash=_signup_ip_hash(settings),
                allow_ip_reuse=_signup_ip_allowlisted(settings),
            )
        except SignupEmailAlreadyExists:
            return _auth_json({"error": "Ja existe uma conta com este e-mail."}, 409)
        except SignupIpLimitExceeded:
            return _auth_json(
                {"error": "Este endereco de IP ja criou uma conta ECloe."},
                403,
            )
        auth_session = repository.create_auth_session(user.user_id)
        repository.get_or_create_demo_session(user.user_id)
        _clear_login_attempts(app, email)
        response = _auth_json({"authenticated": True, "user": asdict(user)})
        _set_auth_cookie(response, auth_session.auth_session_id, settings)
        _set_csrf_cookie(response, settings)
        LOGGER.info("ecloe_pay_register user_id=%s result=success", user.user_id)
        return response

    @app.post("/api/auth/logout")
    def logout():
        if not _csrf_valid():
            return _csrf_error()
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        auth_session_id = request.cookies.get(AUTH_COOKIE_NAME)
        if isinstance(auth_session_id, str):
            auth_session = repository.get_auth_session(auth_session_id)
            repository.revoke_auth_session(auth_session_id)
            if auth_session is not None:
                repository.record_audit_event(auth_session.user_id, "logout", "success")
        logout_url = None
        if settings.ecloe_web_auth_mode == "entra_external":
            logout_url = app.external_identity.logout_url()  # type: ignore[attr-defined]
        response = _auth_json({"authenticated": False, "logout_url": logout_url})
        _clear_auth_cookie(response, settings)
        _set_csrf_cookie(response, settings)
        LOGGER.info("ecloe_pay_logout result=success")
        return response

    @app.get("/api/auth/me")
    def me():
        user, _ = _current_user(app)
        if user is None:
            return _auth_json({"authenticated": False}, 401)
        return _auth_json(
            {
                "authenticated": True,
                "user": user,
                "requires_authentication": app.pay_repository.requires_authentication,  # type: ignore[attr-defined]
                "auth_provider": user.get("auth_provider", settings.ecloe_web_auth_mode),
            }
        )

    @app.get("/api/session")
    def get_session():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        wallet = repository.wallet_snapshot(demo_session.session_id)
        profile = repository.synthetic_profile(demo_session.user_id)
        account = repository.synthetic_account(demo_session.user_id)
        loan_requests = repository.loan_requests(demo_session.user_id)
        benefit_title, benefit_message = PAY_BENEFITS[demo_session.selected_offer_id]
        decision = app.recommendation_decisions.get(demo_session.selected_decision_id, {})  # type: ignore[attr-defined]
        return jsonify(
            {
                "session": asdict(demo_session),
                "wallet": asdict(wallet),
                "profile": asdict(profile) if profile else None,
                "account": asdict(account) if account else None,
                "loan_requests": [asdict(item) for item in loan_requests],
                "benefit": {
                    "title": benefit_title,
                    "message": benefit_message,
                    "offer_id": demo_session.selected_offer_id,
                },
                "recommendation": {
                    "decision_id": demo_session.selected_decision_id,
                    "policy": decision.get("policy", "deterministic_baseline"),
                    "policy_version": decision.get("policy_version", "recommendation-v2"),
                },
                "security": {
                    "user_creation_allowed": False,
                    "real_money_processed": False,
                    "requires_terms": True,
                    "bucket_name": demo_session.bucket_name,
                    "database_provider": "azure_sql" if repository.requires_authentication else "memory",
                    "database_schema": "ecloe_pay",
                },
            }
        )

    @app.post("/api/terms")
    def accept_terms():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        if not _csrf_valid():
            return _csrf_error()
        payload = request.get_json(silent=True) or {}
        if payload.get("accepted") is not True:
            return jsonify({"error": "Terms must be accepted before using ECloe Pay."}), 400
        demo_session = repository.accept_terms(demo_session.session_id)
        return jsonify({"accepted": True, "session_id": demo_session.session_id})

    @app.post("/api/benefit-interactions")
    def create_benefit_interaction():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        if not _csrf_valid():
            return _csrf_error()
        if not demo_session.terms_accepted:
            return jsonify({"error": "Demo terms are required before recording interactions."}), 403

        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip().lower()
        mapping = {
            "open": ("open", 0.0),
            "dismiss": ("rejection", 0.0),
            "accept": ("acceptance", 1.0),
        }
        if action not in mapping:
            return jsonify({"error": "Unsupported benefit action."}), 400

        event_type, reward = mapping[action]
        reward_event = repository.record_benefit_interaction(
            demo_session.session_id,
            event_type,
            reward,
        )
        return jsonify({"reward_event": reward_event, "engine_endpoint": "POST /v2/feedback"})

    @app.post("/api/payment-orders/<payment_order_id>/simulate")
    def simulate_payment(payment_order_id: str):
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        if not _csrf_valid():
            return _csrf_error()
        if not demo_session.terms_accepted:
            return jsonify({"error": "Demo terms are required before simulating payment."}), 403
        if payment_order_id != demo_session.payment_order_id:
            return jsonify({"error": "Payment order was not found in this demo session."}), 404

        payload = request.get_json(silent=True) or {}
        result, reward_event = repository.simulate_payment(
            demo_session.session_id,
            str(payload.get("confirmation_code", "")).strip(),
        )
        if result == "duplicate":
            return jsonify({"error": "Duplicate simulated payment blocked by idempotency."}), 409
        if result == "terms_required":
            return jsonify({"error": "Demo terms are required before simulating payment."}), 403
        if result == "rejected":
            return jsonify({"status": "rejected", "reason": "confirmation_code_mismatch"}), 400

        return jsonify(
            {
                "status": "verified",
                "payment_order": {
                    "payment_order_id": demo_session.payment_order_id,
                    "market_order_id": demo_session.market_order_id,
                    "amount_cents": demo_session.payment_amount_cents,
                    "currency": "BRL",
                    "idempotency_key": demo_session.idempotency_key,
                },
                "bucket_name": demo_session.bucket_name,
                "database_provider": "azure_sql" if repository.requires_authentication else "memory",
                "database_schema": "ecloe_pay",
                "reward_event": reward_event,
            }
        )

    @app.post("/api/reset")
    def reset_session():
        repository: PayRepository = app.pay_repository  # type: ignore[attr-defined]
        demo_session, response, status = _session_or_error(app)
        if response is not None:
            return response, status
        if not _csrf_valid():
            return _csrf_error()
        new_session = repository.reset_demo_state(demo_session.session_id)
        return jsonify({"reset": True, "session_id": new_session.session_id})

    return app


def create_server_app() -> Flask:
    return create_app(settings=load_settings())


app = create_server_app() if os.getenv("FLASK_RUN_FROM_CLI") == "true" else create_app()


if __name__ == "__main__":
    app = create_server_app()
    app.run(host="127.0.0.1", port=5000, debug=False)
