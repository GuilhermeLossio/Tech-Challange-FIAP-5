from __future__ import annotations

from enum import StrEnum

from src.api.schemas.base import StrictApiModel


class ErrorCode(StrEnum):
    invalid_request = "invalid_request"
    idempotency_conflict = "idempotency_conflict"
    unauthorized = "unauthorized"
    forbidden = "forbidden"
    artifact_unavailable = "artifact_unavailable"
    internal_error = "internal_error"


class ErrorResponse(StrictApiModel):
    code: ErrorCode
    message: str
