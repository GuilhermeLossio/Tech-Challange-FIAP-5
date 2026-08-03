from __future__ import annotations

from src.market.application.catalog_loader import load_catalog
from src.market.domain import Category, Product
from src.market.repositories.protocols import MarketRepository


class MemoryMarketRepository(MarketRepository):
    def __init__(self, catalog_path) -> None:
        catalog = load_catalog(catalog_path)
        self.categories = catalog.categories
        self.products = catalog.products

    def list_categories(self) -> list[Category]:
        return list(self.categories)

    def list_products(
        self,
        *,
        category_id: str | None = None,
        query: str | None = None,
    ) -> list[Product]:
        products = [product for product in self.products if product.active]
        if category_id:
            products = [product for product in products if product.category_id == category_id]
        if query:
            normalized_query = query.strip().lower()
            products = [
                product
                for product in products
                if normalized_query in product.title_pt.lower()
                or normalized_query in product.title_en.lower()
                or normalized_query in product.description_pt.lower()
                or normalized_query in product.description_en.lower()
            ]
        return products

    def get_product(self, product_id: str) -> Product | None:
        return next((product for product in self.products if product.product_id == product_id), None)
