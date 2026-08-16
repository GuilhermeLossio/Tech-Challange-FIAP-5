from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "data" / "demo" / "ecloe_market_catalog.json"
DEFAULT_SOURCES = ROOT_DIR / "data" / "demo" / "CATALOG_SOURCES.md"
DEFAULT_ASSETS_DIR = ROOT_DIR / "src" / "demo" / "ecloe_market" / "assets" / "catalog"
DEFAULT_SEED = 426
DUMMYJSON_URL = "https://dummyjson.com/products?limit=60"
KAGGLE_DATASET_SLUG = "fatihkgg/ecommerce-product-images-18k"
KAGGLE_DATASET_URL = "https://www.kaggle.com/datasets/fatihkgg/ecommerce-product-images-18k"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
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
    image_path: Path | None = None
    image_bytes: bytes | None = None
    image_suffix: str = ".svg"


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


def _display_title_from_image(path: str, category: str, index: int) -> str:
    stem = Path(path).stem
    cleaned = re.sub(r"[_\-]+", " ", stem)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned or cleaned.isdigit():
        cleaned = category.replace("_", " ").replace("-", " ")
    return f"{cleaned.title()} {index:02d}"


def _category_from_kaggle_label(label: str, index: int) -> str:
    normalized = label.lower()
    if any(token in normalized for token in ["fashion", "clothing", "shoe", "apparel", "wear"]):
        return "womens-shoes"
    if any(token in normalized for token in ["electronic", "phone", "computer", "camera"]):
        return "mobile-accessories"
    if any(token in normalized for token in ["beauty", "health", "personal"]):
        return "beauty"
    if any(token in normalized for token in ["home", "furniture", "kitchen"]):
        return "home-decoration"
    if any(token in normalized for token in ["grocery", "food"]):
        return "groceries"
    source_categories = list(CATEGORY_BY_SOURCE)
    return source_categories[index % len(source_categories)]


def _kaggle_dir_products(dataset_dir: Path) -> list[SourceProduct]:
    image_paths = sorted(
        path
        for path in dataset_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    return [
        SourceProduct(
            source_id=str(path.relative_to(dataset_dir)).replace("\\", "/"),
            title=_display_title_from_image(str(path), path.parent.name, index),
            description="Image-backed product from the Kaggle ecommerce product images dataset.",
            category=_category_from_kaggle_label(path.parent.name, index),
            price=Decimal("29.90") + Decimal(index * 2) + Decimal((index % 11) * 0.41),
            rating=Decimal("4.0") + Decimal(index % 9) / Decimal("10"),
            image_path=path,
            image_suffix=path.suffix.lower(),
        )
        for index, path in enumerate(image_paths[:60], start=1)
    ]


def _kaggle_archive_products(archive_path: Path) -> list[SourceProduct]:
    products: list[SourceProduct] = []
    with zipfile.ZipFile(archive_path) as archive:
        image_names = sorted(
            name
            for name in archive.namelist()
            if not name.endswith("/") and Path(name).suffix.lower() in IMAGE_EXTENSIONS
        )
        for index, name in enumerate(image_names[:60], start=1):
            label = Path(name).parent.name or "product"
            products.append(
                SourceProduct(
                    source_id=name,
                    title=_display_title_from_image(name, label, index),
                    description="Image-backed product from the Kaggle ecommerce product images dataset.",
                    category=_category_from_kaggle_label(label, index),
                    price=Decimal("29.90") + Decimal(index * 2) + Decimal((index % 11) * 0.41),
                    rating=Decimal("4.0") + Decimal(index % 9) / Decimal("10"),
                    image_bytes=archive.read(name),
                    image_suffix=Path(name).suffix.lower(),
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


def _write_fallback_svg(path: Path, *, product_id: str, title: str, category_id: str) -> None:
    palette = {
        "cat_beauty": ("#ff7fab", "#ffe3ef"),
        "cat_home": ("#9ee7d4", "#e2f8f1"),
        "cat_tech": ("#6aa7ff", "#e4f0ff"),
        "cat_grocery": ("#72c267", "#e6f7df"),
        "cat_wellness": ("#b889ff", "#f0e5ff"),
        "cat_style": ("#ffe18a", "#fff5cf"),
    }
    accent, background = palette.get(category_id, ("#9ee7d4", "#e2f8f1"))
    short_title = title[:26]
    path.write_text(
        "\n".join(
            [
                '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="480" viewBox="0 0 480 480" role="img">',
                f'<rect width="480" height="480" rx="36" fill="{background}"/>',
                f'<circle cx="360" cy="112" r="74" fill="{accent}" opacity="0.55"/>',
                '<rect x="104" y="128" width="272" height="220" rx="28" fill="#ffffff" stroke="#073f36" stroke-width="8"/>',
                f'<path d="M150 292h180M162 210h156M190 250h100" stroke="{accent}" stroke-width="18" stroke-linecap="round"/>',
                '<path d="M126 362h228" stroke="#073f36" stroke-width="10" stroke-linecap="round"/>',
                f'<text x="240" y="414" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="700" fill="#064437">{short_title}</text>',
                f'<text x="240" y="446" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="18" fill="#31564f">{product_id}</text>',
                "</svg>",
            ]
        ),
        encoding="utf-8",
    )


def _materialize_product_image(
    source_product: SourceProduct,
    *,
    product_id: str,
    category_id: str,
    assets_dir: Path,
) -> str:
    assets_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_product.image_suffix if source_product.image_suffix in IMAGE_EXTENSIONS else ".svg"
    output_path = assets_dir / f"{product_id}{suffix}"
    if source_product.image_path is not None:
        shutil.copy2(source_product.image_path, output_path)
    elif source_product.image_bytes is not None:
        output_path.write_bytes(source_product.image_bytes)
    else:
        output_path = assets_dir / f"{product_id}.svg"
        _write_fallback_svg(
            output_path,
            product_id=product_id,
            title=source_product.title,
            category_id=category_id,
        )
    return f"/market/assets/catalog/{output_path.name}"


def normalize_catalog(
    source_products: list[SourceProduct],
    *,
    seed: int,
    assets_dir: Path,
    source_name: str,
    source_url: str,
) -> dict[str, Any]:
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
        image_url = _materialize_product_image(
            source_product,
            product_id=product_id,
            category_id=category_id,
            assets_dir=assets_dir,
        )
        products.append(
            {
                "product_id": product_id,
                "source": source_name,
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
                "thumbnail": image_url,
                "images": [image_url],
                "is_demo": True,
                "status": "active",
            }
        )
    return {
        "metadata": {
            "source": source_name,
            "source_url": source_url,
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


def write_sources(path: Path, *, mode: str, seed: int, source_url: str) -> None:
    path.write_text(
        "\n".join(
            [
                "# ECloe Market Catalog Sources",
                "",
                f"- Source URL: {source_url}",
                f"- Import mode: {mode}",
                f"- Deterministic seed: {seed}",
                "- Kaggle target dataset: `fatihkgg/ecommerce-product-images-18k`.",
                "- Kaggle dataset license as published by Kaggle source page: Apache 2.0.",
                "- ECloe changes: brands, prices, stock, SKUs, and display copy are synthetic demo values.",
                "- Image rule: product image assets are copied into `src/demo/ecloe_market/assets/catalog/` for local beta runtime.",
                "- Runtime rule: the ECloe Market app and tests use `ecloe_market_catalog.json` only.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def generate_catalog(
    *,
    output: Path,
    sources_path: Path,
    seed: int,
    fetch_dummyjson: bool,
    kaggle_dir: Path | None = None,
    kaggle_archive: Path | None = None,
    assets_dir: Path = DEFAULT_ASSETS_DIR,
) -> dict[str, Any]:
    mode = "local generated ecommerce-image fallback"
    source_name = "ecommerce_product_images_18k_local_fallback"
    source_url = KAGGLE_DATASET_URL
    if kaggle_dir is not None and kaggle_dir.exists():
        source_products = _kaggle_dir_products(kaggle_dir)
        mode = f"Kaggle local directory: {kaggle_dir}"
        source_name = "kaggle_ecommerce_product_images_18k"
    elif kaggle_archive is not None and kaggle_archive.exists():
        source_products = _kaggle_archive_products(kaggle_archive)
        mode = f"Kaggle local archive: {kaggle_archive}"
        source_name = "kaggle_ecommerce_product_images_18k"
    elif fetch_dummyjson:
        source_products = _fetch_dummyjson()
        mode = "DummyJSON live fetch with local generated product images"
        source_name = "dummyjson"
        source_url = DUMMYJSON_URL
    else:
        source_products = _offline_products()
    if not source_products:
        raise RuntimeError("No source products were found for ECloe Market catalog generation.")
    catalog = normalize_catalog(
        source_products,
        seed=seed,
        assets_dir=assets_dir,
        source_name=source_name,
        source_url=source_url,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_sources(sources_path, mode=mode, seed=seed, source_url=source_url)
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--fetch-dummyjson", action="store_true")
    parser.add_argument("--kaggle-dir", type=Path)
    parser.add_argument("--kaggle-archive", type=Path)
    args = parser.parse_args()

    catalog = generate_catalog(
        output=args.output,
        sources_path=args.sources,
        seed=args.seed,
        fetch_dummyjson=args.fetch_dummyjson,
        kaggle_dir=args.kaggle_dir,
        kaggle_archive=args.kaggle_archive,
        assets_dir=args.assets_dir,
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
