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
class ProductVariant:
    variant_id: str
    product_id: str
    sku: str
    title_pt: str
    title_en: str
    is_default: bool
    is_demo: bool = True
    status: str = "active"

    @property
    def active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True)
class ProductPrice:
    price_id: str
    variant_id: str
    price_cents: int
    currency: str
    is_current: bool
    is_demo: bool = True


@dataclass(frozen=True)
class InventoryItem:
    inventory_id: str
    variant_id: str
    available_quantity: int
    reserved_quantity: int
    is_demo: bool = True

    @property
    def total_quantity(self) -> int:
        return self.available_quantity + self.reserved_quantity


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


@dataclass(frozen=True)
class ProductDetail:
    product: Product
    variants: tuple[ProductVariant, ...]
    current_prices: tuple[ProductPrice, ...]
    inventory_items: tuple[InventoryItem, ...]

    @property
    def default_variant(self) -> ProductVariant | None:
        return next((variant for variant in self.variants if variant.is_default), None)

    @property
    def current_price(self) -> ProductPrice | None:
        default_variant = self.default_variant
        if default_variant is None:
            return None
        return next(
            (
                price
                for price in self.current_prices
                if price.variant_id == default_variant.variant_id and price.is_current
            ),
            None,
        )

    @property
    def inventory(self) -> InventoryItem | None:
        default_variant = self.default_variant
        if default_variant is None:
            return None
        return next(
            (item for item in self.inventory_items if item.variant_id == default_variant.variant_id),
            None,
        )
