from __future__ import annotations

from src.core.config import Settings
from src.market.repositories.azure_sql import AzureSqlMarketRepository
from src.market.repositories.memory import MemoryMarketRepository
from src.market.repositories.protocols import MarketRepository


def create_market_repository(settings: Settings) -> MarketRepository:
    if settings.ecloe_market_database_mode == "memory":
        return MemoryMarketRepository(settings.ecloe_market_catalog_path)
    if settings.ecloe_market_database_mode == "azure_sql":
        return AzureSqlMarketRepository(settings)
    raise RuntimeError(f"Unsupported ECLOE_MARKET_DATABASE_MODE: {settings.ecloe_market_database_mode}")
