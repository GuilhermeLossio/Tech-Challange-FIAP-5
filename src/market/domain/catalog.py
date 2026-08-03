from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    category_id: str
    slug: str
    title_pt: str
    title_en: str
    is_demo: bool = True


@dataclass(frozen=True)
class Product:
    product_id: str
    source: str
    source_id: str
    slug: str
    title_pt: str
    title_en: str
    description_pt: str
    description_en: str
    category_id: str
    brand: str
    sku: str
    price_cents: int
    currency: str
    stock_quantity: int
    rating: float
    thumbnail: str
    images: tuple[str, ...]
    is_demo: bool
    status: str

    @property
    def active(self) -> bool:
        return self.status == "active"
