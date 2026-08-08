from __future__ import annotations

import os

from flask import Flask

from src.core.config import Settings, load_settings
from src.demo.ecloe_market.blueprint import market_blueprint
from src.demo.ecloe_pay.app import create_app as create_pay_app
from src.demo.ecloe_pay.repositories import PayRepository
from src.market.repositories import MarketRepository, create_market_repository


def create_app(
    settings: Settings | None = None,
    *,
    pay_repository: PayRepository | None = None,
    market_repository: MarketRepository | None = None,
) -> Flask:
    settings = settings or load_settings(use_env_file=False)
    app = create_pay_app(settings=settings, repository=pay_repository)
    app.market_repository = market_repository or create_market_repository(settings)  # type: ignore[attr-defined]
    app.register_blueprint(market_blueprint)
    return app


def create_server_app() -> Flask:
    return create_app(settings=load_settings())


app = create_server_app() if os.getenv("FLASK_RUN_FROM_CLI") == "true" else create_app()


if __name__ == "__main__":
    app = create_server_app()
    app.run(host="127.0.0.1", port=5000, debug=False)
