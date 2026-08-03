from __future__ import annotations

import argparse
import json
import random
import re
import urllib.request
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "data" / "demo" / "ecloe_market_catalog.json"
DEFAULT_SOURCES = ROOT_DIR / "data" / "demo" / "CATALOG_SOURCES.md"
DEFAULT_SEED = 426
DUMMYJSON_URL = "https://dummyjson.com/products?limit=60"
FICTIONAL_BRANDS = [
    "Cloe & Co.",
    "Minty Home",
    "Rosette Beauty",
    "Lemon Lab",
    "ECloe Essentials",
    "Clover Tech",
]
CATEGORIES = [
    ("cat_beauty", "beauty", "Beleza", "Beauty"),
    ("cat_home", "home", "Casa", "Home"),
    ("cat_tech", "tech", "Tecnologia", "Tech"),
    ("cat_grocery", "grocery", "Mercado", "Grocery"),
    ("cat_wellness", "wellness", "Bem-estar", "Wellness"),
    ("cat_style", "style", "Estilo", "Style"),
]
CATEGORY_BY_SOURCE = {
    "beauty": "cat_beauty",
    "fragrances": "cat_beauty",
    "skin-care": "cat_wellness",
    "furniture": "cat_home",
    "home-decoration": "cat_home",
    "kitchen-accessories": "cat_home",
    "laptops": "cat_tech",
    "smartphones": "cat_tech",
    "mobile-accessories": "cat_tech",
    "groceries": "cat_grocery",
    "womens-dresses": "cat_style",
    "womens-shoes": "cat_style",
    "mens-shirts": "cat_style",
    "mens-shoes": "cat_style",
}


@dataclass(frozen=True)
class SourceProduct:
    source_id: str
    title: str
    description: str
    category: str
    price: Decimal
    rating: Decimal


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "demo-product"


def _price_cents(value: Decimal) -> int:
    cents = (value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _offline_products() -> list[SourceProduct]:
    titles = [
        "Glow balm",
        "Mint desk lamp",
        "Clover keyboard",
        "Lemon pantry kit",
        "Rosette serum",
        "Cloe tote",
        "Smart herb pot",
        "Daily care set",
        "Soft linen throw",
        "Pocket speaker",
    ]
    descriptions = [
        "Synthetic catalog item for the ECloe Market demo journey.",
        "Demo-only product used to validate catalog, cart, and checkout behavior.",
        "Simulated marketplace item with reproducible price and stock.",
    ]
    source_categories = list(CATEGORY_BY_SOURCE)
    products: list[SourceProduct] = []
    for index in range(60):
        category = source_categories[index % len(source_categories)]
        base_price = Decimal("19.90") + Decimal(index * 3) + Decimal((index % 7) * 0.35)
        products.append(
            SourceProduct(
                source_id=str(index + 1),
                title=f"{titles[index % len(titles)]} {index + 1:02d}",
                description=descriptions[index % len(descriptions)],
                category=category,
                price=base_price,
                rating=Decimal("4.1") + Decimal(index % 8) / Decimal("10"),
            )
        )
    return products


def _fetch_dummyjson() -> list[SourceProduct]:
    with urllib.request.urlopen(DUMMYJSON_URL, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    products = []
    for raw in payload.get("products", []):
        products.append(
            SourceProduct(
                source_id=str(raw["id"]),
                title=str(raw["title"]),
                description=str(raw["description"]),
                category=str(raw["category"]),
                price=Decimal(str(raw["price"])),
                rating=Decimal(str(raw.get("rating", "4.0"))),
            )
        )
    return products[:60]


def normalize_catalog(source_products: list[SourceProduct], *, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    categories = [
        {
            "category_id": category_id,
            "slug": slug,
            "title_pt": title_pt,
            "title_en": title_en,
            "is_demo": True,
        }
        for category_id, slug, title_pt, title_en in CATEGORIES
    ]
    products = []
    for index, source_product in enumerate(source_products[:60], start=1):
        product_id = f"prd_demo_{index:04d}"
        category_id = CATEGORY_BY_SOURCE.get(source_product.category, CATEGORIES[index % len(CATEGORIES)][0])
        title_en = source_product.title.strip()
        title_pt = f"{title_en} demonstrativo"
        stock_quantity = 6 + ((index * 7 + rng.randint(0, 4)) % 19)
        products.append(
            {
                "product_id": product_id,
                "source": "dummyjson",
                "source_id": source_product.source_id,
                "slug": f"{_slug(title_en)}-{index:04d}",
                "title_pt": title_pt,
                "title_en": title_en,
                "description_pt": "Produto sintetico para validacao do ECloe Market.",
                "description_en": source_product.description,
                "category_id": category_id,
                "brand": FICTIONAL_BRANDS[(index - 1) % len(FICTIONAL_BRANDS)],
                "sku": f"ECLOE-{index:04d}",
                "price_cents": _price_cents(source_product.price),
                "currency": "BRL",
                "stock_quantity": stock_quantity,
                "rating": float(source_product.rating.quantize(Decimal("0.1"))),
                "thumbnail": "/market/assets/product-placeholder.svg",
                "images": ["/market/assets/product-placeholder.svg"],
                "is_demo": True,
                "status": "active",
            }
        )
    return {
        "metadata": {
            "source": "dummyjson",
            "source_url": DUMMYJSON_URL,
            "seed": seed,
            "generated_at": "2026-08-03T00:00:00+00:00",
            "synthetic_notice": (
                "All products, brands, prices, stock values, and ratings are synthetic "
                "demo data for ECloe Market."
            ),
        },
        "categories": categories,
        "products": products,
    }


def write_sources(path: Path, *, fetched: bool, seed: int) -> None:
    mode = "DummyJSON live fetch" if fetched else "offline DummyJSON-compatible fixture"
    path.write_text(
        "\n".join(
            [
                "# ECloe Market Catalog Sources",
                "",
                f"- Source URL: {DUMMYJSON_URL}",
                f"- Import mode: {mode}",
                f"- Deterministic seed: {seed}",
                "- License/terms: DummyJSON public demo API; verify upstream terms before production use.",
                "- ECloe changes: brands, prices, stock, SKUs, and display copy are synthetic demo values.",
                "- Runtime rule: the ECloe Market app and tests use `ecloe_market_catalog.json` only.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def generate_catalog(*, output: Path, sources_path: Path, seed: int, fetch_dummyjson: bool) -> dict[str, Any]:
    fetched = False
    if fetch_dummyjson:
        source_products = _fetch_dummyjson()
        fetched = True
    else:
        source_products = _offline_products()
    catalog = normalize_catalog(source_products, seed=seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_sources(sources_path, fetched=fetched, seed=seed)
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--fetch-dummyjson", action="store_true")
    args = parser.parse_args()

    catalog = generate_catalog(
        output=args.output,
        sources_path=args.sources,
        seed=args.seed,
        fetch_dummyjson=args.fetch_dummyjson,
    )
    print(
        json.dumps(
            {
                "products": len(catalog["products"]),
                "categories": len(catalog["categories"]),
                "output": str(args.output),
                "sources": str(args.sources),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
