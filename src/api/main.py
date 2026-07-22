from __future__ import annotations

from fastapi import FastAPI

from src.api.dependencies import create_lifespan
from src.api.errors import register_error_handlers
from src.api.middleware import register_middleware
from src.api.routers import decisions, health, likelihoods, policies, rewards
from src.engine import DecisionService


def create_app(decision_service: DecisionService | None = None) -> FastAPI:
    app = FastAPI(
        title="ECloe Engine API",
        version="0.1.0",
        lifespan=create_lifespan(decision_service),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    if decision_service is not None:
        app.state.decision_service = decision_service

    register_middleware(app)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(policies.router)
    app.include_router(likelihoods.router)
    app.include_router(decisions.router)
    app.include_router(rewards.router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
