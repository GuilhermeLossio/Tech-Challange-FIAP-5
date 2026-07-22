from __future__ import annotations

from fastapi import FastAPI

from src.api.dependencies import create_lifespan
from src.api.errors import register_error_handlers
from src.api.middleware import register_middleware
from src.api.observability import configure_observability
from src.api.routers import decisions, health, likelihoods, policies, rewards
from src.core.config import load_settings
from src.engine import DecisionService
from src.storage.decision_repository import DecisionRepository


def create_app(
    decision_service: DecisionService | None = None,
    decision_repository: DecisionRepository | None = None,
) -> FastAPI:
    app = FastAPI(
        title="ECloe Engine API",
        version="0.1.0",
        lifespan=create_lifespan(decision_service, decision_repository),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    if decision_service is not None:
        app.state.decision_service = decision_service
    if decision_repository is not None:
        app.state.decision_repository = decision_repository

    configure_observability(app, load_settings())
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

    from src.core.config import load_settings

    settings = load_settings()
    uvicorn.run("src.api.main:app", host=settings.api_host, port=8000, reload=False)


if __name__ == "__main__":
    main()
