from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ecloe_market_shared_visual_tokens_exist() -> None:
    shared_core = (ROOT / "src" / "demo" / "shared" / "core.css").read_text(encoding="utf-8")
    pay_core = (ROOT / "src" / "demo" / "ecloe_pay" / "core.css").read_text(encoding="utf-8")
    market_css = (
        ROOT / "src" / "demo" / "ecloe_market" / "assets" / "market.css"
    ).read_text(encoding="utf-8")

    for token in [
        "--font-display: \"Baloo 2\"",
        "--font-body: Nunito",
        "--font-mono: \"Space Mono\"",
        "--color-ink: #073f36",
        "--color-heading: #064437",
        "--color-page: #f7fcf7",
        "--color-rose: #ff7fab",
        "--color-mint: #9ee7d4",
        "--color-lemon: #ffe18a",
    ]:
        assert token in shared_core
    assert "--color-ink: #073f36" in pay_core
    assert '@import url("/shared/core.css");' in market_css


def test_ecloe_market_static_files_do_not_request_real_financial_data() -> None:
    market_files = [
        ROOT / "src" / "demo" / "ecloe_market" / "market_index.html",
        ROOT / "src" / "demo" / "ecloe_market" / "market_product.html",
        ROOT / "src" / "demo" / "ecloe_market" / "market_cart.html",
        ROOT / "src" / "demo" / "ecloe_market" / "market_planned.html",
        ROOT / "src" / "demo" / "ecloe_market" / "market_summary.html",
        ROOT / "src" / "demo" / "ecloe_market" / "assets" / "market.css",
        ROOT / "src" / "demo" / "ecloe_market" / "assets" / "market.js",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in market_files)

    for forbidden in ["cpf", "cvv", "agencia", "senha bancaria"]:
        assert forbidden not in combined


def test_ecloe_market_i18n_files_exist() -> None:
    i18n_dir = ROOT / "src" / "demo" / "ecloe_market" / "i18n"
    assert (i18n_dir / "pt-BR.json").exists()
    assert (i18n_dir / "en-US.json").exists()


def test_ecloe_market_azure_sql_schema_has_pr2_tables_and_constraints() -> None:
    schema = (ROOT / "src" / "market" / "infrastructure" / "schema.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE SCHEMA ecloe_market" in schema
    for table in [
        "schema_migrations",
        "categories",
        "products",
        "product_variants",
        "product_prices",
        "inventory_items",
        "carts",
        "cart_items",
        "checkout_sessions",
        "orders",
        "order_items",
        "payment_references",
        "outbox_events",
    ]:
        assert f"ecloe_market.{table}" in schema
    for constraint in [
        "CHECK (is_demo = 1)",
        "CHECK (currency = 'BRL')",
        "CHECK (price_cents >= 0)",
        "CHECK (stock_quantity >= 0)",
        "CHECK (available_quantity >= 0)",
        "CHECK (reserved_quantity >= 0)",
        "UNIQUE (slug)",
        "UNIQUE (sku)",
    ]:
        assert constraint in schema
    assert "ecloe_pay" not in schema


def test_ecloe_market_class_diagram_matches_domain_and_schema() -> None:
    diagram = (ROOT / "docs" / "ecloe-market-class-diagram.svg").read_text(encoding="utf-8")
    domain_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "market" / "domain").glob("*.py")
    )
    schema = (ROOT / "src" / "market" / "infrastructure" / "schema.sql").read_text(
        encoding="utf-8"
    )

    for class_name in [
        "Category",
        "Product",
        "ProductVariant",
        "ProductPrice",
        "InventoryItem",
        "Cart",
        "CartItem",
        "CheckoutSession",
        "Order",
        "OrderItem",
        "PaymentReference",
        "MarketplaceEvent",
        "OutboxEvent",
    ]:
        assert class_name in diagram
        assert f"class {class_name}" in domain_sources
    for table_name in [
        "carts",
        "cart_items",
        "checkout_sessions",
        "orders",
        "order_items",
        "payment_references",
        "outbox_events",
    ]:
        assert f"ecloe_market.{table_name}" in schema


def test_ecloe_market_home_uses_marketplace_layout_not_pay_sidebar_only() -> None:
    html = (ROOT / "src" / "demo" / "ecloe_market" / "market_index.html").read_text(
        encoding="utf-8"
    )

    assert "marketplace-header" in html
    assert "marketplace-search" in html
    assert "marketplace-results" in html
    assert "marketplace-filters" in html
    assert "market-sidebar" not in html


def test_ecloe_market_images_use_catalog_gallery_layout() -> None:
    index_html = (ROOT / "src" / "demo" / "ecloe_market" / "market_index.html").read_text(
        encoding="utf-8"
    )
    product_html = (ROOT / "src" / "demo" / "ecloe_market" / "market_product.html").read_text(
        encoding="utf-8"
    )
    market_css = (
        ROOT / "src" / "demo" / "ecloe_market" / "assets" / "market.css"
    ).read_text(encoding="utf-8")
    market_js = (ROOT / "src" / "demo" / "ecloe_market" / "assets" / "market.js").read_text(
        encoding="utf-8"
    )

    assert "product-image-panel" in index_html
    assert "product-card-thumbs" in index_html
    assert "data-product-gallery-main" in product_html
    assert "data-gallery-image" in product_html
    assert "object-fit: contain" in market_css
    assert "data-gallery-image" in market_js


def test_ecloe_market_runtime_uses_repository_factory() -> None:
    app_source = (ROOT / "src" / "demo" / "app.py").read_text(encoding="utf-8")
    factory_source = (ROOT / "src" / "market" / "repositories" / "factory.py").read_text(
        encoding="utf-8"
    )

    assert "create_market_repository(settings)" in app_source
    assert "ECLOE_MARKET_DATABASE_MODE" in factory_source
    assert "AzureSqlMarketRepository" in factory_source
