from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.market.domain import Category, Product


@dataclass(frozen=True)
class Catalog:
    categories: list[Category]
    products: list[Product]
    metadata: dict[str, Any]


def load_catalog(path: Path | str) -> Catalog:
    catalog_path = Path(path)
    with catalog_path.open(encoding="utf-8") as source:
        payload = json.load(source)

    categories = [Category(**category) for category in payload.get("categories", [])]
    products = [
        Product(
            **{
                **product,
                "images": tuple(product.get("images", [])),
            }
        )
        for product in payload.get("products", [])
    ]
    return Catalog(categories=categories, products=products, metadata=payload.get("metadata", {}))
