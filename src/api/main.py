from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.engine import DecisionService
from src.engine.artifacts import ArtifactValidationError
from src.engine.schemas import EngineRequest
from src.engine.validation import validate_engine_request


class EngineRequestPayload(BaseModel):
    request_id: str = Field(min_length=1)
    customer_context: dict[str, Any]
    eligible_offers: list[str]


def _engine_request(payload: EngineRequestPayload) -> EngineRequest:
    return EngineRequest(
        request_id=payload.request_id,
        customer_context=payload.customer_context,
        eligible_offers=payload.eligible_offers,
    )


def create_app(decision_service: DecisionService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.decision_service = decision_service or DecisionService.from_files()
        yield

    app = FastAPI(title="ECloe Engine API", version="0.1.0", lifespan=lifespan)
    if decision_service is not None:
        app.state.decision_service = decision_service

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "ecloe-engine"}

    @app.get("/v1/policy")
    def policy() -> dict[str, object]:
        try:
            return _decision_service(app).current_policy()
        except (ArtifactValidationError, FileNotFoundError) as error:
            raise _artifact_unavailable(error) from error

    @app.post("/v1/purchase-likelihood")
    def purchase_likelihood(payload: EngineRequestPayload) -> dict[str, object]:
        try:
            request = _engine_request(payload)
            validate_engine_request(request)
            response = _decision_service(app).likelihood_service.estimate(request)
        except (ArtifactValidationError, FileNotFoundError) as error:
            raise _artifact_unavailable(error) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(error)}) from error
        return asdict(response)

    @app.post("/v1/decisions")
    def decisions(payload: EngineRequestPayload) -> dict[str, object]:
        try:
            request = _engine_request(payload)
            validate_engine_request(request)
            response = _decision_service(app).decide(request)
        except (ArtifactValidationError, FileNotFoundError) as error:
            raise _artifact_unavailable(error) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(error)}) from error
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
        detail={"code": "artifact_unavailable", "message": str(error)},
    )


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
