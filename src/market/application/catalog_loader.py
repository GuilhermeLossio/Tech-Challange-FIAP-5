from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.market.domain import Category, InventoryItem, Product, ProductPrice, ProductVariant


@dataclass(frozen=True)
class Catalog:
    categories: list[Category]
    products: list[Product]
    variants: list[ProductVariant]
    prices: list[ProductPrice]
    inventory_items: list[InventoryItem]
    metadata: dict[str, Any]


def load_catalog(path: Path | str) -> Catalog:
    catalog_path = Path(path)
    with catalog_path.open(encoding="utf-8") as source:
        payload = json.load(source)

    categories = [Category(**category) for category in payload.get("categories", [])]
    products = []
    variants = []
    prices = []
    inventory_items = []
    for product_payload in payload.get("products", []):
        product = Product(
            **{
                **product_payload,
                "images": tuple(product_payload.get("images", [])),
            }
        )
        _validate_product(product)
        products.append(product)

        product_variants = product_payload.get("variants") or [_default_variant_payload(product)]
        for variant_payload in product_variants:
            variant_fields = {
                key: value
                for key, value in variant_payload.items()
                if key not in {"prices", "inventory"}
            }
            variant = ProductVariant(**variant_fields)
            variants.append(variant)
            price_payloads = variant_payload.get("prices") or [_default_price_payload(product, variant)]
            for price_payload in price_payloads:
                price = ProductPrice(**price_payload)
                _validate_price(price)
                prices.append(price)
            inventory_payload = variant_payload.get("inventory") or _default_inventory_payload(product, variant)
            inventory = InventoryItem(**inventory_payload)
            _validate_inventory(inventory)
            inventory_items.append(inventory)

    return Catalog(
        categories=categories,
        products=products,
        variants=variants,
        prices=prices,
        inventory_items=inventory_items,
        metadata=payload.get("metadata", {}),
    )


def _default_variant_payload(product: Product) -> dict[str, object]:
    return {
        "variant_id": f"var_{product.product_id.removeprefix('prd_')}_default",
        "product_id": product.product_id,
        "sku": product.sku,
        "title_pt": "Padrao demonstrativo",
        "title_en": "Default demo",
        "is_default": True,
        "is_demo": product.is_demo,
        "status": product.status,
    }


def _default_price_payload(product: Product, variant: ProductVariant) -> dict[str, object]:
    return {
        "price_id": f"price_{variant.variant_id}",
        "variant_id": variant.variant_id,
        "price_cents": product.price_cents,
        "currency": product.currency,
        "is_current": True,
        "is_demo": product.is_demo,
    }


def _default_inventory_payload(product: Product, variant: ProductVariant) -> dict[str, object]:
    return {
        "inventory_id": f"inv_{variant.variant_id}",
        "variant_id": variant.variant_id,
        "available_quantity": product.stock_quantity,
        "reserved_quantity": 0,
        "is_demo": product.is_demo,
    }


def _validate_product(product: Product) -> None:
    if not product.is_demo:
        raise ValueError(f"{product.product_id} must be marked as demo data.")
    if not isinstance(product.price_cents, int) or product.price_cents < 0:
        raise ValueError(f"{product.product_id} must use non-negative integer price_cents.")
    if product.currency != "BRL":
        raise ValueError(f"{product.product_id} must use BRL currency.")
    if not isinstance(product.stock_quantity, int) or product.stock_quantity < 0:
        raise ValueError(f"{product.product_id} must use non-negative integer stock_quantity.")


def _validate_price(price: ProductPrice) -> None:
    if not isinstance(price.price_cents, int) or price.price_cents < 0:
        raise ValueError(f"{price.price_id} must use non-negative integer price_cents.")
    if price.currency != "BRL":
        raise ValueError(f"{price.price_id} must use BRL currency.")
    if not price.is_demo:
        raise ValueError(f"{price.price_id} must be marked as demo data.")


def _validate_inventory(inventory: InventoryItem) -> None:
    if inventory.available_quantity < 0 or inventory.reserved_quantity < 0:
        raise ValueError(f"{inventory.inventory_id} must use non-negative inventory quantities.")
    if not inventory.is_demo:
        raise ValueError(f"{inventory.inventory_id} must be marked as demo data.")
