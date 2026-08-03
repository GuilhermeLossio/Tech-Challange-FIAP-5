from __future__ import annotations

from typing import Protocol

from src.market.domain import Category, Product


class MarketRepository(Protocol):
    def list_categories(self) -> list[Category]:
        ...

    def list_products(
        self,
        *,
        category_id: str | None = None,
        query: str | None = None,
    ) -> list[Product]:
        ...

    def get_product(self, product_id: str) -> Product | None:
        ...
