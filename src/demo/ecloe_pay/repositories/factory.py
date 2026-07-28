from __future__ import annotations

from src.core.config import Settings
from src.demo.ecloe_pay.repositories.azure_sql import AzureSqlPayRepository
from src.demo.ecloe_pay.repositories.base import PayRepository
from src.demo.ecloe_pay.repositories.memory import MemoryPayRepository


def create_pay_repository(settings: Settings) -> PayRepository:
    if settings.ecloe_pay_database_mode == "memory":
        return MemoryPayRepository(settings)
    if settings.ecloe_pay_database_mode == "azure_sql":
        return AzureSqlPayRepository(settings)
    raise RuntimeError(f"Unsupported ECLOE_PAY_DATABASE_MODE: {settings.ecloe_pay_database_mode}")
