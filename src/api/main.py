from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.engine import DecisionService, PurchaseLikelihoodService
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


def create_app() -> FastAPI:
    app = FastAPI(title="ECloe Engine API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "ecloe-engine"}

    @app.get("/v1/policy")
    def policy() -> dict[str, object]:
        try:
            return DecisionService.from_files().current_policy()
        except FileNotFoundError as error:
            raise HTTPException(status_code=503, detail={"code": "artifact_missing", "message": str(error)}) from error

    @app.post("/v1/purchase-likelihood")
    def purchase_likelihood(payload: EngineRequestPayload) -> dict[str, object]:
        try:
            request = _engine_request(payload)
            validate_engine_request(request)
            response = PurchaseLikelihoodService.from_file().estimate(request)
        except FileNotFoundError as error:
            raise HTTPException(status_code=503, detail={"code": "artifact_missing", "message": str(error)}) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(error)}) from error
        return asdict(response)

    @app.post("/v1/decisions")
    def decisions(payload: EngineRequestPayload) -> dict[str, object]:
        try:
            request = _engine_request(payload)
            validate_engine_request(request)
            response = DecisionService.from_files().decide(request)
        except FileNotFoundError as error:
            raise HTTPException(status_code=503, detail={"code": "artifact_missing", "message": str(error)}) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(error)}) from error
        return asdict(response)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
