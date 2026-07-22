from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.engine import DecisionService
from src.engine.artifacts import ArtifactValidationError
from src.engine.schemas import EngineRequest
from src.engine.validation import validate_engine_request
from src.api.schemas import (
    DecisionRequest,
    DecisionResponse,
    ErrorCode,
    ErrorResponse,
    HealthResponse,
    PolicyResponse,
    PurchaseLikelihoodResponse,
)


API_ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _engine_request(payload: DecisionRequest) -> EngineRequest:
    return EngineRequest(
        request_id=payload.request_id,
        customer_context=payload.customer_context.model_dump(exclude_none=True, mode="json"),
        eligible_offers=[offer.value for offer in payload.eligible_offers],
    )


def create_app(decision_service: DecisionService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.decision_service = decision_service or DecisionService.from_files()
        yield

    app = FastAPI(title="ECloe Engine API", version="0.1.0", lifespan=lifespan)
    if decision_service is not None:
        app.state.decision_service = decision_service

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, error: RequestValidationError) -> JSONResponse:
        return _error_response(422, ErrorCode.invalid_request, _validation_message(error))

    @app.exception_handler(ArtifactValidationError)
    async def artifact_validation_handler(_: Request, error: ArtifactValidationError) -> JSONResponse:
        return _error_response(503, ErrorCode.artifact_unavailable, str(error))

    @app.exception_handler(FileNotFoundError)
    async def artifact_missing_handler(_: Request, error: FileNotFoundError) -> JSONResponse:
        return _error_response(503, ErrorCode.artifact_unavailable, str(error))

    @app.exception_handler(Exception)
    async def internal_error_handler(_: Request, error: Exception) -> JSONResponse:
        return _error_response(500, ErrorCode.internal_error, str(error))

    @app.get("/health", response_model=HealthResponse, responses=API_ERROR_RESPONSES)
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "ecloe-engine"}

    @app.get("/v1/policy", response_model=PolicyResponse, responses=API_ERROR_RESPONSES)
    def policy() -> dict[str, object]:
        try:
            return _decision_service(app).current_policy()
        except (ArtifactValidationError, FileNotFoundError) as error:
            raise _artifact_unavailable(error) from error

    @app.post(
        "/v1/purchase-likelihood",
        response_model=PurchaseLikelihoodResponse,
        responses=API_ERROR_RESPONSES,
    )
    def purchase_likelihood(payload: DecisionRequest) -> dict[str, object]:
        try:
            request = _engine_request(payload)
            validate_engine_request(request)
            response = _decision_service(app).likelihood_service.estimate(request)
        except (ArtifactValidationError, FileNotFoundError) as error:
            raise _artifact_unavailable(error) from error
        except ValueError as error:
            raise _invalid_request(error) from error
        return asdict(response)

    @app.post("/v1/decisions", response_model=DecisionResponse, responses=API_ERROR_RESPONSES)
    def decisions(payload: DecisionRequest) -> dict[str, object]:
        try:
            request = _engine_request(payload)
            validate_engine_request(request)
            response = _decision_service(app).decide(request)
        except (ArtifactValidationError, FileNotFoundError) as error:
            raise _artifact_unavailable(error) from error
        except ValueError as error:
            raise _invalid_request(error) from error
        return asdict(response)

    return app


def _decision_service(app: FastAPI) -> DecisionService:
    service = getattr(app.state, "decision_service", None)
    if service is None:
        service = DecisionService.from_files()
        app.state.decision_service = service
    return service


def _artifact_unavailable(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=ErrorResponse(code=ErrorCode.artifact_unavailable, message=str(error)).model_dump(mode="json"),
    )


def _invalid_request(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail=ErrorResponse(code=ErrorCode.invalid_request, message=str(error)).model_dump(mode="json"),
    )


def _error_response(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
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


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
