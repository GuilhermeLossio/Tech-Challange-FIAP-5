import asyncio
import json
import time
from dataclasses import replace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.middleware import register_middleware
from src.core.config import load_settings
from src.core.rate_limit import SharedRateLimiter
from src.demo.ecloe_pay.app import CSRF_COOKIE_NAME, create_app
from src.demo.ecloe_pay.repositories import MemoryPayRepository


def _csrf(client) -> dict[str, str]:
    cookie = client.get_cookie(CSRF_COOKIE_NAME)
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def test_csrf_is_stable_until_authentication_rotates_it() -> None:
    client = create_app().test_client()
    client.get("/pay/login")
    first = client.get_cookie(CSRF_COOKIE_NAME)
    client.get("/pay/login")
    second = client.get_cookie(CSRF_COOKIE_NAME)
    assert first is not None and second is not None
    assert first.value == second.value

    response = client.post(
        "/api/auth/login",
        json={"email": "demo.market@ecloe.local", "password": "change-this-demo-password"},
        headers={"X-CSRF-Token": first.value},
    )
    assert response.status_code == 200
    rotated = client.get_cookie(CSRF_COOKIE_NAME)
    assert rotated is not None and rotated.value != first.value


def test_password_policy_rejects_short_and_overlong_passwords() -> None:
    settings = replace(load_settings(use_env_file=False), ecloe_web_auth_mode="local_signup")
    app = create_app(settings=settings, repository=MemoryPayRepository(settings))
    client = app.test_client()
    client.get("/pay/register")

    for password in ("short-pass", "x" * 129):
        response = client.post(
            "/api/auth/register",
            json={"email": f"{len(password)}@example.com", "password": password, "password_confirm": password},
            headers=_csrf(client),
        )
        assert response.status_code == 400


def test_shared_limiter_expires_counters() -> None:
    settings = replace(load_settings(use_env_file=False), rate_limit_backend="memory")
    limiter = SharedRateLimiter(settings)
    assert limiter.allow("test", 1, 1)
    assert not limiter.allow("test", 1, 1)
    time.sleep(1.05)
    assert limiter.allow("test", 1, 1)


def test_payload_limit_applies_without_content_length(monkeypatch) -> None:
    monkeypatch.setenv("MAX_PAYLOAD_BYTES", "4")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        return JSONResponse({"size": len(await request.body())})

    register_middleware(app, replace(load_settings(use_env_file=False), max_payload_bytes=4))
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"12345", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "method": "POST",
                "path": "/echo",
                "raw_path": b"/echo",
                "query_string": b"",
                "headers": [(b"host", b"127.0.0.1")],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
                "scheme": "http",
                "http_version": "1.1",
            },
            receive,
            send,
        )
    )
    body = next(message["body"] for message in sent if message["type"] == "http.response.body")
    assert any(message.get("status") == 413 for message in sent)
    assert json.loads(body) == {
        "code": "invalid_request",
        "message": "Payload is too large.",
    }
