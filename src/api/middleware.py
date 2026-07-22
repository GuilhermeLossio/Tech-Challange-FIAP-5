from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from time import monotonic

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request

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

    @app.middleware("http")
    async def abuse_protection(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                payload_size = int(content_length)
            except ValueError:
                return _limit_response(400, "Invalid Content-Length header.")
            if payload_size > settings.max_payload_bytes:
                return _limit_response(413, "Payload is too large.")

        client = request.client.host if request.client else "unknown"
        now = monotonic()
        timestamps = request_log[client]
        while timestamps and now - timestamps[0] > settings.rate_limit_window_seconds:
            timestamps.popleft()
        if len(timestamps) >= settings.rate_limit_requests:
            return _limit_response(429, "Rate limit exceeded.")
        timestamps.append(now)

        if semaphore.locked():
            return _limit_response(429, "Too many concurrent requests.")

        async with semaphore:
            return await call_next(request)


def _limit_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": "invalid_request", "message": message},
    )
