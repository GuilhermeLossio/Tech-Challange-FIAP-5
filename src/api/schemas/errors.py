from __future__ import annotations

from enum import Enum

from src.api.schemas.base import StrictApiModel


class ErrorCode(str, Enum):
    invalid_request = "invalid_request"
    unauthorized = "unauthorized"
    forbidden = "forbidden"
    artifact_unavailable = "artifact_unavailable"
    internal_error = "internal_error"


class ErrorResponse(StrictApiModel):
    code: ErrorCode
    message: str
