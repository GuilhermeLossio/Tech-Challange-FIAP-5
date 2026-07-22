from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.schemas.errors import ErrorCode, ErrorResponse
from src.engine.artifacts import ArtifactValidationError


API_ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}

ARTIFACT_UNAVAILABLE_MESSAGE = "Required serving artifact is unavailable or invalid."
INTERNAL_ERROR_MESSAGE = "Internal server error."


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail
        if isinstance(detail, dict) and {"code", "message"} <= set(detail):
            return JSONResponse(status_code=error.status_code, content=detail, headers=error.headers)
        return error_response(error.status_code, ErrorCode.invalid_request, str(detail))

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(422, ErrorCode.invalid_request, _validation_message(error))

    @app.exception_handler(ArtifactValidationError)
    async def artifact_validation_handler(_: Request, __: ArtifactValidationError) -> JSONResponse:
        return error_response(503, ErrorCode.artifact_unavailable, ARTIFACT_UNAVAILABLE_MESSAGE)

    @app.exception_handler(FileNotFoundError)
    async def artifact_missing_handler(_: Request, __: FileNotFoundError) -> JSONResponse:
        return error_response(503, ErrorCode.artifact_unavailable, ARTIFACT_UNAVAILABLE_MESSAGE)

    @app.exception_handler(Exception)
    async def internal_error_handler(_: Request, __: Exception) -> JSONResponse:
        return error_response(500, ErrorCode.internal_error, INTERNAL_ERROR_MESSAGE)


def artifact_unavailable(_: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=ErrorResponse(
            code=ErrorCode.artifact_unavailable,
            message=ARTIFACT_UNAVAILABLE_MESSAGE,
        ).model_dump(mode="json"),
    )


def invalid_request(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail=ErrorResponse(code=ErrorCode.invalid_request, message=str(error)).model_dump(mode="json"),
    )


def error_response(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(code=code, message=message).model_dump(mode="json"),
    )


def _validation_message(error: RequestValidationError) -> str:
    messages = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        messages.append(f"{location}: {item.get('msg', 'invalid value')}")
    return "; ".join(messages)
