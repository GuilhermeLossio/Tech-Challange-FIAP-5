from pathlib import Path

from src.core.config import load_settings
from src.market.repositories import MemoryMarketRepository


ROOT = Path(__file__).resolve().parents[1]


def test_memory_market_repository_filters_products() -> None:
    settings = load_settings(use_env_file=False)
    repository = MemoryMarketRepository(settings.ecloe_market_catalog_path)

    beauty_products = repository.list_products(category_id="cat_beauty", limit=60)
    query_products = repository.list_products(query="Glow", limit=60)

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


def test_memory_market_repository_sorts_and_paginates_products() -> None:
    settings = load_settings(use_env_file=False)
    repository = MemoryMarketRepository(settings.ecloe_market_catalog_path)

    lowest = repository.list_products(sort="price_asc", limit=5)
    highest = repository.list_products(sort="price_desc", limit=5)
    second_page = repository.list_products(sort="featured", limit=5, offset=5)

    assert [product.price_cents for product in lowest] == sorted(product.price_cents for product in lowest)
    assert [product.price_cents for product in highest] == sorted(
        (product.price_cents for product in highest),
        reverse=True,
    )
    assert len(second_page) == 5
    assert {product.product_id for product in second_page}.isdisjoint(
        {product.product_id for product in repository.list_products(sort="featured", limit=5)}
    )


def test_memory_market_repository_gets_product_detail_with_price_and_stock() -> None:
    settings = load_settings(use_env_file=False)
    repository = MemoryMarketRepository(settings.ecloe_market_catalog_path)

    detail = repository.get_product_detail("prd_demo_0001")

    assert detail is not None
    assert detail.product.product_id == "prd_demo_0001"
    assert detail.default_variant is not None
    assert detail.current_price is not None
    assert detail.current_price.price_cents == detail.product.price_cents
    assert isinstance(detail.current_price.price_cents, int)
    assert detail.inventory is not None
    assert detail.inventory.available_quantity == detail.product.stock_quantity
    assert repository.get_product_detail("prd_missing") is None


def test_memory_market_repository_manages_demo_cart() -> None:
    settings = load_settings(use_env_file=False)
    repository = MemoryMarketRepository(settings.ecloe_market_catalog_path)

    empty_cart = repository.get_cart("market_sess_test")
    cart = repository.add_cart_item(session_key="market_sess_test", product_id="prd_demo_0001")
    updated = repository.update_cart_item(
        session_key="market_sess_test",
        cart_item_id=cart.items[0].cart_item_id,
        quantity=3,
    )
    removed = repository.remove_cart_item(
        session_key="market_sess_test",
        cart_item_id=cart.items[0].cart_item_id,
    )

    assert empty_cart.empty is True
    assert cart.total_items == 1
    assert cart.total_cents == cart.items[0].unit_price_cents
    assert isinstance(cart.total_cents, int)
    assert updated.total_items == 3
    assert removed.empty is True


def test_azure_market_repository_uses_available_transaction_context() -> None:
    source = (ROOT / "src" / "market" / "repositories" / "azure_sql.py").read_text(encoding="utf-8")

    assert "with self.engine.begin() as connection:" in source
    assert "self._transaction()" not in source
