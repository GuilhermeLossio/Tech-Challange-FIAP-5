IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ecloe_market')
BEGIN
    EXEC(N'CREATE SCHEMA ecloe_market');
END;
GO

IF OBJECT_ID(N'ecloe_market.schema_migrations', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.schema_migrations (
        migration_id NVARCHAR(160) NOT NULL CONSTRAINT pk_market_schema_migrations PRIMARY KEY,
        applied_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_schema_migrations_applied_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00'))
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.categories', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.categories (
        category_id NVARCHAR(64) NOT NULL CONSTRAINT pk_market_categories PRIMARY KEY,
        slug NVARCHAR(120) NOT NULL,
        title_pt NVARCHAR(160) NOT NULL,
        title_en NVARCHAR(160) NOT NULL,
        sort_order INT NOT NULL CONSTRAINT df_market_categories_sort_order DEFAULT 0,
        is_demo BIT NOT NULL CONSTRAINT df_market_categories_is_demo DEFAULT 1,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_categories_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_categories_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT uq_market_categories_slug UNIQUE (slug),
        CONSTRAINT ck_market_categories_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.products', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.products (
        product_id NVARCHAR(64) NOT NULL CONSTRAINT pk_market_products PRIMARY KEY,
        source NVARCHAR(80) NOT NULL,
        source_id NVARCHAR(80) NOT NULL,
        slug NVARCHAR(160) NOT NULL,
        title_pt NVARCHAR(220) NOT NULL,
        title_en NVARCHAR(220) NOT NULL,
        description_pt NVARCHAR(1000) NOT NULL,
        description_en NVARCHAR(1000) NOT NULL,
        category_id NVARCHAR(64) NOT NULL,
        brand NVARCHAR(120) NOT NULL,
        sku NVARCHAR(80) NOT NULL,
        price_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_market_products_currency DEFAULT 'BRL',
        stock_quantity INT NOT NULL,
        rating DECIMAL(3, 2) NOT NULL,
        thumbnail NVARCHAR(260) NOT NULL,
        images_json NVARCHAR(MAX) NOT NULL,
        is_demo BIT NOT NULL CONSTRAINT df_market_products_is_demo DEFAULT 1,
        status NVARCHAR(20) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_products_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_products_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_market_products_categories
            FOREIGN KEY (category_id) REFERENCES ecloe_market.categories(category_id),
        CONSTRAINT uq_market_products_slug UNIQUE (slug),
        CONSTRAINT uq_market_products_sku UNIQUE (sku),
        CONSTRAINT ck_market_products_price CHECK (price_cents >= 0),
        CONSTRAINT ck_market_products_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_market_products_stock CHECK (stock_quantity >= 0),
        CONSTRAINT ck_market_products_is_demo CHECK (is_demo = 1),
        CONSTRAINT ck_market_products_status CHECK (status IN (N'active', N'inactive')),
        CONSTRAINT ck_market_products_images_json CHECK (ISJSON(images_json) = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.product_variants', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.product_variants (
        variant_id NVARCHAR(80) NOT NULL CONSTRAINT pk_market_product_variants PRIMARY KEY,
        product_id NVARCHAR(64) NOT NULL,
        sku NVARCHAR(80) NOT NULL,
        title_pt NVARCHAR(180) NOT NULL,
        title_en NVARCHAR(180) NOT NULL,
        is_default BIT NOT NULL CONSTRAINT df_market_product_variants_is_default DEFAULT 0,
        is_demo BIT NOT NULL CONSTRAINT df_market_product_variants_is_demo DEFAULT 1,
        status NVARCHAR(20) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_product_variants_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_product_variants_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_market_product_variants_products
            FOREIGN KEY (product_id) REFERENCES ecloe_market.products(product_id),
        CONSTRAINT uq_market_product_variants_sku UNIQUE (sku),
        CONSTRAINT ck_market_product_variants_is_demo CHECK (is_demo = 1),
        CONSTRAINT ck_market_product_variants_status CHECK (status IN (N'active', N'inactive'))
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.product_prices', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.product_prices (
        price_id NVARCHAR(100) NOT NULL CONSTRAINT pk_market_product_prices PRIMARY KEY,
        variant_id NVARCHAR(80) NOT NULL,
        price_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_market_product_prices_currency DEFAULT 'BRL',
        is_current BIT NOT NULL CONSTRAINT df_market_product_prices_is_current DEFAULT 1,
        is_demo BIT NOT NULL CONSTRAINT df_market_product_prices_is_demo DEFAULT 1,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_product_prices_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_product_prices_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_market_product_prices_variants
            FOREIGN KEY (variant_id) REFERENCES ecloe_market.product_variants(variant_id),
        CONSTRAINT ck_market_product_prices_price CHECK (price_cents >= 0),
        CONSTRAINT ck_market_product_prices_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_market_product_prices_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.inventory_items', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.inventory_items (
        inventory_id NVARCHAR(100) NOT NULL CONSTRAINT pk_market_inventory_items PRIMARY KEY,
        variant_id NVARCHAR(80) NOT NULL,
        available_quantity INT NOT NULL,
        reserved_quantity INT NOT NULL CONSTRAINT df_market_inventory_items_reserved_quantity DEFAULT 0,
        is_demo BIT NOT NULL CONSTRAINT df_market_inventory_items_is_demo DEFAULT 1,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_inventory_items_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_inventory_items_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_market_inventory_items_variants
            FOREIGN KEY (variant_id) REFERENCES ecloe_market.product_variants(variant_id),
        CONSTRAINT uq_market_inventory_items_variant UNIQUE (variant_id),
        CONSTRAINT ck_market_inventory_items_available CHECK (available_quantity >= 0),
        CONSTRAINT ck_market_inventory_items_reserved CHECK (reserved_quantity >= 0),
        CONSTRAINT ck_market_inventory_items_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.carts', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.carts (
        cart_id NVARCHAR(80) NOT NULL CONSTRAINT pk_market_carts PRIMARY KEY,
        session_key_hash NVARCHAR(128) NOT NULL,
        user_id NVARCHAR(64) NULL,
        status NVARCHAR(20) NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_market_carts_currency DEFAULT 'BRL',
        is_demo BIT NOT NULL CONSTRAINT df_market_carts_is_demo DEFAULT 1,
        expires_at DATETIMEOFFSET(7) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_carts_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_carts_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT ck_market_carts_status CHECK (status IN (N'active', N'checkout_started', N'ordered', N'abandoned')),
        CONSTRAINT ck_market_carts_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_market_carts_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.cart_items', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.cart_items (
        cart_item_id NVARCHAR(100) NOT NULL CONSTRAINT pk_market_cart_items PRIMARY KEY,
        cart_id NVARCHAR(80) NOT NULL,
        product_id NVARCHAR(64) NOT NULL,
        variant_id NVARCHAR(80) NOT NULL,
        quantity INT NOT NULL,
        unit_price_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_market_cart_items_currency DEFAULT 'BRL',
        is_demo BIT NOT NULL CONSTRAINT df_market_cart_items_is_demo DEFAULT 1,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_cart_items_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_cart_items_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_market_cart_items_carts
            FOREIGN KEY (cart_id) REFERENCES ecloe_market.carts(cart_id),
        CONSTRAINT fk_market_cart_items_products
            FOREIGN KEY (product_id) REFERENCES ecloe_market.products(product_id),
        CONSTRAINT fk_market_cart_items_variants
            FOREIGN KEY (variant_id) REFERENCES ecloe_market.product_variants(variant_id),
        CONSTRAINT uq_market_cart_items_variant UNIQUE (cart_id, variant_id),
        CONSTRAINT ck_market_cart_items_quantity CHECK (quantity BETWEEN 1 AND 99),
        CONSTRAINT ck_market_cart_items_price CHECK (unit_price_cents >= 0),
        CONSTRAINT ck_market_cart_items_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_market_cart_items_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.checkout_sessions', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.checkout_sessions (
        checkout_id NVARCHAR(80) NOT NULL CONSTRAINT pk_market_checkout_sessions PRIMARY KEY,
        cart_id NVARCHAR(80) NOT NULL,
        user_id NVARCHAR(64) NOT NULL,
        status NVARCHAR(24) NOT NULL,
        total_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_market_checkout_sessions_currency DEFAULT 'BRL',
        idempotency_key NVARCHAR(180) NOT NULL,
        correlation_id NVARCHAR(80) NOT NULL,
        context_snapshot_json NVARCHAR(MAX) NOT NULL,
        is_demo BIT NOT NULL CONSTRAINT df_market_checkout_sessions_is_demo DEFAULT 1,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_checkout_sessions_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_checkout_sessions_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_market_checkout_sessions_carts
            FOREIGN KEY (cart_id) REFERENCES ecloe_market.carts(cart_id),
        CONSTRAINT uq_market_checkout_sessions_idempotency UNIQUE (idempotency_key),
        CONSTRAINT ck_market_checkout_sessions_status CHECK (status IN (N'created', N'payment_pending', N'paid', N'payment_failed', N'cancelled')),
        CONSTRAINT ck_market_checkout_sessions_total CHECK (total_cents >= 0),
        CONSTRAINT ck_market_checkout_sessions_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_market_checkout_sessions_context CHECK (ISJSON(context_snapshot_json) = 1),
        CONSTRAINT ck_market_checkout_sessions_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.orders', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.orders (
        order_id NVARCHAR(80) NOT NULL CONSTRAINT pk_market_orders PRIMARY KEY,
        checkout_id NVARCHAR(80) NOT NULL,
        user_id NVARCHAR(64) NOT NULL,
        status NVARCHAR(24) NOT NULL,
        total_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_market_orders_currency DEFAULT 'BRL',
        correlation_id NVARCHAR(80) NOT NULL,
        is_demo BIT NOT NULL CONSTRAINT df_market_orders_is_demo DEFAULT 1,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_orders_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_orders_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_market_orders_checkout_sessions
            FOREIGN KEY (checkout_id) REFERENCES ecloe_market.checkout_sessions(checkout_id),
        CONSTRAINT ck_market_orders_status CHECK (status IN (N'created', N'payment_pending', N'paid', N'payment_failed', N'cancelled', N'refunded')),
        CONSTRAINT ck_market_orders_total CHECK (total_cents >= 0),
        CONSTRAINT ck_market_orders_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_market_orders_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.order_items', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.order_items (
        order_item_id NVARCHAR(100) NOT NULL CONSTRAINT pk_market_order_items PRIMARY KEY,
        order_id NVARCHAR(80) NOT NULL,
        product_id NVARCHAR(64) NOT NULL,
        variant_id NVARCHAR(80) NOT NULL,
        title_snapshot NVARCHAR(220) NOT NULL,
        quantity INT NOT NULL,
        unit_price_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_market_order_items_currency DEFAULT 'BRL',
        is_demo BIT NOT NULL CONSTRAINT df_market_order_items_is_demo DEFAULT 1,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_order_items_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_market_order_items_orders
            FOREIGN KEY (order_id) REFERENCES ecloe_market.orders(order_id),
        CONSTRAINT ck_market_order_items_quantity CHECK (quantity BETWEEN 1 AND 99),
        CONSTRAINT ck_market_order_items_price CHECK (unit_price_cents >= 0),
        CONSTRAINT ck_market_order_items_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_market_order_items_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.payment_references', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.payment_references (
        payment_reference_id NVARCHAR(100) NOT NULL CONSTRAINT pk_market_payment_references PRIMARY KEY,
        order_id NVARCHAR(80) NOT NULL,
        pay_payment_order_id NVARCHAR(80) NOT NULL,
        status NVARCHAR(24) NOT NULL,
        amount_cents INT NOT NULL,
        currency CHAR(3) NOT NULL CONSTRAINT df_market_payment_references_currency DEFAULT 'BRL',
        is_demo BIT NOT NULL CONSTRAINT df_market_payment_references_is_demo DEFAULT 1,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_payment_references_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_payment_references_updated_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_market_payment_references_orders
            FOREIGN KEY (order_id) REFERENCES ecloe_market.orders(order_id),
        CONSTRAINT uq_market_payment_references_pay_order UNIQUE (pay_payment_order_id),
        CONSTRAINT ck_market_payment_references_status CHECK (status IN (N'created', N'verified', N'rejected', N'cancelled', N'refunded')),
        CONSTRAINT ck_market_payment_references_amount CHECK (amount_cents >= 0),
        CONSTRAINT ck_market_payment_references_currency CHECK (currency = 'BRL'),
        CONSTRAINT ck_market_payment_references_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF OBJECT_ID(N'ecloe_market.outbox_events', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_market.outbox_events (
        outbox_event_id NVARCHAR(100) NOT NULL CONSTRAINT pk_market_outbox_events PRIMARY KEY,
        aggregate_id NVARCHAR(100) NOT NULL,
        event_type NVARCHAR(80) NOT NULL,
        payload_json NVARCHAR(MAX) NOT NULL,
        status NVARCHAR(24) NOT NULL CONSTRAINT df_market_outbox_events_status DEFAULT N'pending',
        is_demo BIT NOT NULL CONSTRAINT df_market_outbox_events_is_demo DEFAULT 1,
        occurred_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_market_outbox_events_occurred_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        published_at DATETIMEOFFSET(7) NULL,
        CONSTRAINT ck_market_outbox_events_payload CHECK (ISJSON(payload_json) = 1),
        CONSTRAINT ck_market_outbox_events_status CHECK (status IN (N'pending', N'published', N'failed')),
        CONSTRAINT ck_market_outbox_events_is_demo CHECK (is_demo = 1)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_market_products_category' AND object_id = OBJECT_ID(N'ecloe_market.products')
)
BEGIN
    CREATE INDEX ix_market_products_category
        ON ecloe_market.products (category_id, status, product_id);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_market_product_prices_current' AND object_id = OBJECT_ID(N'ecloe_market.product_prices')
)
BEGIN
    CREATE INDEX ix_market_product_prices_current
        ON ecloe_market.product_prices (variant_id, is_current);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_market_carts_session' AND object_id = OBJECT_ID(N'ecloe_market.carts')
)
BEGIN
    CREATE INDEX ix_market_carts_session
        ON ecloe_market.carts (session_key_hash, status);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_market_outbox_events_pending' AND object_id = OBJECT_ID(N'ecloe_market.outbox_events')
)
BEGIN
    CREATE INDEX ix_market_outbox_events_pending
        ON ecloe_market.outbox_events (occurred_at)
        WHERE published_at IS NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM ecloe_market.schema_migrations WHERE migration_id = N'20260803_ecloe_market_catalog_pr2'
)
BEGIN
    INSERT INTO ecloe_market.schema_migrations (migration_id)
    VALUES (N'20260803_ecloe_market_catalog_pr2');
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM ecloe_market.schema_migrations WHERE migration_id = N'20260803_ecloe_market_platform_classes'
)
BEGIN
    INSERT INTO ecloe_market.schema_migrations (migration_id)
    VALUES (N'20260803_ecloe_market_platform_classes');
END;
GO
