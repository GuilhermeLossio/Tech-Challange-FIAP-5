from __future__ import annotations

import hashlib

from src.market.application.catalog_loader import load_catalog
from src.market.domain import Cart, CartItem, Category, Product, ProductDetail
from src.market.repositories.protocols import MarketRepository

ALLOWED_SORTS = {"featured", "price_asc", "price_desc", "title"}


class MemoryMarketRepository(MarketRepository):
    def __init__(self, catalog_path) -> None:
        catalog = load_catalog(catalog_path)
        self.categories = catalog.categories
        self.products = catalog.products
        self.variants = catalog.variants
        self.prices = catalog.prices
        self.inventory_items = catalog.inventory_items
        self._carts: dict[str, Cart] = {}

    def list_categories(self) -> list[Category]:
        return list(self.categories)

    def list_products(
        self,
        *,
        category_id: str | None = None,
        query: str | None = None,
        sort: str = "featured",
        limit: int = 24,
        offset: int = 0,
    ) -> list[Product]:
        products = [product for product in self.products if product.active]
        if category_id:
            products = [product for product in products if product.category_id == category_id]
        if query:
            normalized_query = query.strip().lower()
            products = [
                product
                for product in products
                if normalized_query in product.title_pt.lower()
                or normalized_query in product.title_en.lower()
                or normalized_query in product.description_pt.lower()
                or normalized_query in product.description_en.lower()
            ]
        products = _sort_products(products, sort)
        safe_offset = max(offset, 0)
        safe_limit = max(min(limit, 60), 1)
        return products[safe_offset : safe_offset + safe_limit]

    def get_product(self, product_id: str) -> Product | None:
        return next((product for product in self.products if product.product_id == product_id), None)

    def get_product_detail(self, product_id: str) -> ProductDetail | None:
        product = self.get_product(product_id)
        if product is None:
            return None
        variants = tuple(
            variant for variant in self.variants if variant.product_id == product.product_id and variant.active
        )
        variant_ids = {variant.variant_id for variant in variants}
        prices = tuple(
            price for price in self.prices if price.variant_id in variant_ids and price.is_current
        )
        inventory_items = tuple(
            item for item in self.inventory_items if item.variant_id in variant_ids
        )
        return ProductDetail(
            product=product,
            variants=variants,
            current_prices=prices,
            inventory_items=inventory_items,
        )

    def get_cart(self, session_key: str) -> Cart:
        cart = self._carts.get(session_key)
        if cart is not None:
            return cart
        return Cart(
            cart_id=_cart_id(session_key),
            session_key=session_key,
            status="active",
            items=(),
        )

    def add_cart_item(
        self,
        *,
        session_key: str,
        product_id: str,
        variant_id: str | None = None,
        quantity: int = 1,
    ) -> Cart:
        detail = self.get_product_detail(product_id)
        if detail is None:
            raise ValueError("Synthetic ECloe Market product was not found.")
        selected_variant = detail.default_variant
        if variant_id:
            selected_variant = next(
                (variant for variant in detail.variants if variant.variant_id == variant_id),
                None,
            )
        if selected_variant is None:
            raise ValueError("Synthetic ECloe Market variant was not found.")
        price = next(
            (
                price
                for price in detail.current_prices
                if price.variant_id == selected_variant.variant_id and price.is_current
            ),
            None,
        )
        if price is None:
            raise ValueError("Synthetic ECloe Market price was not found.")

        cart = self.get_cart(session_key)
        safe_quantity = max(min(quantity, 9), 1)
        cart_item_id = _cart_item_id(cart.cart_id, selected_variant.variant_id)
        existing = next((item for item in cart.items if item.cart_item_id == cart_item_id), None)
        items = [item for item in cart.items if item.cart_item_id != cart_item_id]
        new_quantity = safe_quantity + (existing.quantity if existing else 0)
        items.append(
            CartItem(
                cart_item_id=cart_item_id,
                cart_id=cart.cart_id,
                product_id=detail.product.product_id,
                variant_id=selected_variant.variant_id,
                title=detail.product.title_en,
                quantity=min(new_quantity, 9),
                unit_price_cents=price.price_cents,
                currency=price.currency,
                thumbnail=detail.product.thumbnail,
            )
        )
        return self._save_cart(cart, tuple(sorted(items, key=lambda item: item.cart_item_id)))

    def update_cart_item(self, *, session_key: str, cart_item_id: str, quantity: int) -> Cart:
        cart = self.get_cart(session_key)
        if quantity <= 0:
            return self.remove_cart_item(session_key=session_key, cart_item_id=cart_item_id)
        items = tuple(
            CartItem(**{**item.__dict__, "quantity": min(quantity, 9)})
            if item.cart_item_id == cart_item_id
            else item
            for item in cart.items
        )
        return self._save_cart(cart, items)

    def remove_cart_item(self, *, session_key: str, cart_item_id: str) -> Cart:
        cart = self.get_cart(session_key)
        items = tuple(item for item in cart.items if item.cart_item_id != cart_item_id)
        return self._save_cart(cart, items)

    def _save_cart(self, cart: Cart, items: tuple[CartItem, ...]) -> Cart:
        updated = Cart(
            cart_id=cart.cart_id,
            session_key=cart.session_key,
            status=cart.status,
            items=items,
            currency=cart.currency,
            is_demo=cart.is_demo,
        )
        self._carts[cart.session_key] = updated
        return updated


def _sort_products(products: list[Product], sort: str) -> list[Product]:
    if sort not in ALLOWED_SORTS:
        sort = "featured"
    if sort == "price_asc":
        return sorted(products, key=lambda product: (product.price_cents, product.title_en))
    if sort == "price_desc":
        return sorted(products, key=lambda product: (-product.price_cents, product.title_en))
    if sort == "title":
        return sorted(products, key=lambda product: product.title_en.lower())
    return sorted(products, key=lambda product: product.product_id)


def _cart_id(session_key: str) -> str:
    digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:16]
    return f"cart_demo_{digest}"


def _cart_item_id(cart_id: str, variant_id: str) -> str:
    digest = hashlib.sha256(f"{cart_id}:{variant_id}".encode()).hexdigest()[:16]
    return f"cart_item_{digest}"
