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
        assert product.source == "dummyjson"
        assert product.title_pt
        assert product.title_en
        assert product.category_id
        assert product.thumbnail.startswith("/market/assets/")
        assert product.images
        assert isinstance(product.price_cents, int)
        assert product.price_cents > 0
        assert product.currency == "BRL"
        assert product.stock_quantity >= 0
        assert product.is_demo is True
        assert product.status == "active"


def test_ecloe_market_catalog_seed_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first_sources = tmp_path / "first.md"
    second_sources = tmp_path / "second.md"

    generate_catalog(output=first, sources_path=first_sources, seed=426, fetch_dummyjson=False)
    generate_catalog(output=second, sources_path=second_sources, seed=426, fetch_dummyjson=False)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert "offline DummyJSON-compatible fixture" in first_sources.read_text(encoding="utf-8")


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
