from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import json
import logging
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request

from src.api.observability import LOGGER_NAME
from src.core.config import load_settings


def register_middleware(app: FastAPI) -> None:
    settings = load_settings()
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
    request_log: dict[str, deque[float]] = defaultdict(deque)
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
        if content_length:
            try:
                payload_size = int(content_length)
            except ValueError:
                response = _limit_response(400, "Invalid Content-Length header.")
                _log_access(request, access_logger, request_id, trace_id, started, response.status_code)
                return response
            if payload_size > settings.max_payload_bytes:
                response = _limit_response(413, "Payload is too large.")
                _log_access(request, access_logger, request_id, trace_id, started, response.status_code)
                return response

        client = request.client.host if request.client else "unknown"
        now = monotonic()
        timestamps = request_log[client]
        while timestamps and now - timestamps[0] > settings.rate_limit_window_seconds:
            timestamps.popleft()
        if len(timestamps) >= settings.rate_limit_requests:
            response = _limit_response(429, "Rate limit exceeded.")
            _log_access(request, access_logger, request_id, trace_id, started, response.status_code)
            return response
        timestamps.append(now)

        if semaphore.locked():
            response = _limit_response(429, "Too many concurrent requests.")
            _log_access(request, access_logger, request_id, trace_id, started, response.status_code)
            return response

        try:
            async with semaphore:
                response = await call_next(request)
                status_code = response.status_code
                response.headers["X-Request-Id"] = request_id
                response.headers["X-Trace-Id"] = trace_id
                return response
        finally:
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
