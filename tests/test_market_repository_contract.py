from src.core.config import load_settings
from src.market.repositories import MemoryMarketRepository


def test_memory_market_repository_filters_products() -> None:
    settings = load_settings(use_env_file=False)
    repository = MemoryMarketRepository(settings.ecloe_market_catalog_path)

    beauty_products = repository.list_products(category_id="cat_beauty")
    query_products = repository.list_products(query="Glow")

    assert beauty_products
    assert all(product.category_id == "cat_beauty" for product in beauty_products)
    assert query_products
    assert all(product.active for product in query_products)


def test_memory_market_repository_gets_product_by_id() -> None:
    settings = load_settings(use_env_file=False)
    repository = MemoryMarketRepository(settings.ecloe_market_catalog_path)

    product = repository.get_product("prd_demo_0001")

    assert product is not None
    assert product.product_id == "prd_demo_0001"
    assert repository.get_product("prd_missing") is None
