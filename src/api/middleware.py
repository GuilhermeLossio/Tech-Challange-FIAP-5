from __future__ import annotations

import asyncio
import json
import logging
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request

from src.api.metrics import metrics_for
from src.api.observability import LOGGER_NAME
from src.core.config import Settings, load_settings
from src.core.rate_limit import RateLimitBackendUnavailable, SharedRateLimiter


def register_middleware(app: FastAPI, settings: Settings | None = None) -> None:
    settings = settings or load_settings(use_env_file=False)
    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    rate_limiter = SharedRateLimiter(settings)
    access_logger = logging.getLogger(LOGGER_NAME)

    @app.middleware("http")
    async def abuse_protection(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        trace_id = _trace_id(request)
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        started = monotonic()
        status_code = 500

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                payload_size = int(content_length)
            except ValueError:
                response = _limit_response(400, "Invalid Content-Length header.")
                _log_access(request, access_logger, request_id, trace_id, started, response.status_code)
                return response
            if payload_size < 0 or payload_size > settings.max_payload_bytes:
                response = _limit_response(413, "Payload is too large.")
                _log_access(request, access_logger, request_id, trace_id, started, response.status_code)
                return response

        client = request.client.host if request.client else "unknown"
        try:
            allowed = rate_limiter.allow(
                f"api:{client}", settings.rate_limit_requests, settings.rate_limit_window_seconds
            )
        except RateLimitBackendUnavailable:
            response = _limit_response(503, "Rate limit protection is unavailable.")
            _log_access(request, access_logger, request_id, trace_id, started, response.status_code)
            return response
        if not allowed:
            response = _limit_response(429, "Rate limit exceeded.")
            _log_access(request, access_logger, request_id, trace_id, started, response.status_code)
            return response

        if semaphore.locked():
            response = _limit_response(429, "Too many concurrent requests.")
            _log_access(request, access_logger, request_id, trace_id, started, response.status_code)
            return response

        try:
            async with semaphore:
                original_receive = request._receive
                received_bytes = 0
                payload_too_large = False

                async def limited_receive():
                    nonlocal received_bytes, payload_too_large
                    message = await original_receive()
                    if message.get("type") == "http.request":
                        received_bytes += len(message.get("body", b""))
                        if received_bytes > settings.max_payload_bytes:
                            payload_too_large = True
                            return {"type": "http.request", "body": b"", "more_body": False}
                    return message

                request._receive = limited_receive
                try:
                    response = await call_next(request)
                finally:
                    if payload_too_large:
                        response = _limit_response(413, "Payload is too large.")
                status_code = response.status_code
                response.headers["X-Request-Id"] = request_id
                response.headers["X-Trace-Id"] = trace_id
                return response
        finally:
            metrics_for(request.app).request(status_code, (monotonic() - started) * 1000)
            _log_access(request, access_logger, request_id, trace_id, started, status_code)


def _limit_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": "invalid_request", "message": message},
    )


def _trace_id(request: Request) -> str:
    try:
        from opentelemetry.trace import get_current_span
    except ModuleNotFoundError:
        return request.headers.get("x-trace-id") or str(uuid4())

    span_context = get_current_span().get_span_context()
    if span_context.is_valid:
        return f"{span_context.trace_id:032x}"
    return request.headers.get("x-trace-id") or str(uuid4())


def _log_access(
    request: Request,
    logger: logging.Logger,
    request_id: str,
    trace_id: str,
    started: float,
    status_code: int,
) -> None:
    if getattr(request.app.state, "observability_enabled", True) is False:
        return

    payload = {
        "request_id": request_id,
        "trace_id": trace_id,
        "decision_id": getattr(request.state, "decision_id", None),
        "route": request.url.path,
        "method": request.method,
        "status": status_code,
        "latency_ms": round((monotonic() - started) * 1000, 3),
        "policy_version": getattr(request.state, "policy_version", None),
    }
    logger.info(json.dumps(payload, sort_keys=True, separators=(",", ":")))
