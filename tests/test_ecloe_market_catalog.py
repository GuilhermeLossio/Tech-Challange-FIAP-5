from pathlib import Path

from scripts.seed_ecloe_market_catalog import generate_catalog
from src.core.config import load_settings
from src.market.application.catalog_loader import load_catalog


def test_ecloe_market_catalog_is_normalized_local_demo_data() -> None:
    settings = load_settings(use_env_file=False)
    catalog = load_catalog(settings.ecloe_market_catalog_path)

    assert len(catalog.products) == 60
    assert len(catalog.categories) == 6
    for product in catalog.products:
        assert product.product_id.startswith("prd_demo_")
        assert product.source in {
            "ecommerce_product_images_18k_local_fallback",
            "kaggle_ecommerce_product_images_18k",
            "dummyjson",
        }
        assert product.title_pt
        assert product.title_en
        assert product.category_id
        assert product.thumbnail.startswith("/market/assets/catalog/")
        assert product.images
        assert isinstance(product.price_cents, int)
        assert product.price_cents > 0
        assert product.currency == "BRL"
        assert product.stock_quantity >= 0
        assert product.is_demo is True
        assert product.status == "active"
    assert {product.thumbnail for product in catalog.products} != {"/market/assets/product-placeholder.svg"}
    assert len(catalog.variants) == len(catalog.products)
    assert len(catalog.prices) == len(catalog.products)
    assert len(catalog.inventory_items) == len(catalog.products)
    for price in catalog.prices:
        assert isinstance(price.price_cents, int)
        assert price.price_cents > 0
        assert price.currency == "BRL"
        assert price.is_current is True
        assert price.is_demo is True
    for inventory in catalog.inventory_items:
        assert isinstance(inventory.available_quantity, int)
        assert inventory.available_quantity >= 0
        assert inventory.reserved_quantity == 0
        assert inventory.is_demo is True


def test_ecloe_market_catalog_seed_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first_sources = tmp_path / "first.md"
    second_sources = tmp_path / "second.md"

    generate_catalog(
        output=first,
        sources_path=first_sources,
        seed=426,
        fetch_dummyjson=False,
        assets_dir=tmp_path / "first_assets",
    )
    generate_catalog(
        output=second,
        sources_path=second_sources,
        seed=426,
        fetch_dummyjson=False,
        assets_dir=tmp_path / "second_assets",
    )

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert "local generated ecommerce-image fallback" in first_sources.read_text(encoding="utf-8")


def test_ecloe_market_catalog_seed_can_use_local_kaggle_image_dir(tmp_path: Path) -> None:
    kaggle_dir = tmp_path / "kaggle" / "Fashion"
    kaggle_dir.mkdir(parents=True)
    image = kaggle_dir / "demo_product.jpg"
    image.write_bytes(b"fake-image")
    output = tmp_path / "catalog.json"
    sources = tmp_path / "sources.md"
    assets = tmp_path / "assets"

    catalog = generate_catalog(
        output=output,
        sources_path=sources,
        seed=426,
        fetch_dummyjson=False,
        kaggle_dir=tmp_path / "kaggle",
        assets_dir=assets,
    )

    assert catalog["products"][0]["source"] == "kaggle_ecommerce_product_images_18k"
    assert catalog["products"][0]["thumbnail"].endswith(".jpg")
    assert (assets / "prd_demo_0001.jpg").read_bytes() == b"fake-image"
    assert "Kaggle local directory" in sources.read_text(encoding="utf-8")


def test_ecloe_market_catalog_uses_fictional_display_brands() -> None:
    settings = load_settings(use_env_file=False)
    catalog = load_catalog(settings.ecloe_market_catalog_path)
    allowed_brands = {
        "Cloe & Co.",
        "Minty Home",
        "Rosette Beauty",
        "Lemon Lab",
        "ECloe Essentials",
        "Clover Tech",
    }

    assert {product.brand for product in catalog.products} <= allowed_brands


def test_ecloe_market_catalog_loader_accepts_azure_blob_image_urls(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.azure.json"
    image_url = (
        "https://acct.blob.core.windows.net/ecloe-market-demo-assets/"
        "catalog/images/prd_demo_0001_01.png"
    )
    catalog_path.write_text(
        """
        {
          "metadata": {},
          "categories": [
            {
              "category_id": "cat_tech",
              "slug": "tech",
              "title_pt": "Tecnologia",
              "title_en": "Tech",
              "is_demo": true
            }
          ],
          "products": [
            {
              "product_id": "prd_demo_0001",
              "source": "test",
              "source_id": "1",
              "slug": "demo",
              "title_pt": "Demo",
              "title_en": "Demo",
              "description_pt": "Demo",
              "description_en": "Demo",
              "category_id": "cat_tech",
              "brand": "ECloe Essentials",
              "sku": "ECLOE-0001",
              "price_cents": 1000,
              "currency": "BRL",
              "stock_quantity": 5,
              "rating": 4.5,
              "thumbnail": "__IMAGE_URL__",
              "images": ["__IMAGE_URL__"],
              "is_demo": true,
              "status": "active"
            }
          ]
        }
        """.replace("__IMAGE_URL__", image_url),
        encoding="utf-8",
    )

    catalog = load_catalog(catalog_path)

    assert catalog.products[0].thumbnail == image_url
    assert catalog.products[0].images == (image_url,)
