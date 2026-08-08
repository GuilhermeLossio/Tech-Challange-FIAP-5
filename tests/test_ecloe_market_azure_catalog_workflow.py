from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from scripts.generate_ecloe_market_catalog_images import (
    HuggingFaceSpaceImageGenerator,
    complete_catalog_images,
)
from scripts.publish_ecloe_market_catalog_to_azure import publish_catalog_to_blob
from scripts.seed_ecloe_market_catalog import generate_catalog
from src.market.application.catalog_loader import load_catalog


def test_ecloe_market_image_completion_generates_three_images_per_product(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    output_path = tmp_path / "catalog.completed.json"
    assets_dir = tmp_path / "assets"
    generate_catalog(
        output=catalog_path,
        sources_path=tmp_path / "sources.md",
        seed=426,
        fetch_dummyjson=False,
        assets_dir=tmp_path / "seed_assets",
    )

    summary = complete_catalog_images(
        catalog_path=catalog_path,
        output_path=output_path,
        assets_dir=assets_dir,
        model_dir=tmp_path / "model",
        seed=426,
        generator=FakeImageGenerator(),
    )
    catalog = load_catalog(output_path)

    assert summary.products_updated == 60
    assert summary.images_generated == 180
    for product in catalog.products:
        assert len(product.images) == 3
        assert product.thumbnail == product.images[0]
        assert all(image.startswith("/market/assets/catalog/") for image in product.images)
        assert all(image.endswith(".png") for image in product.images)


def test_ecloe_market_image_completion_reuses_existing_generated_files(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    existing = assets_dir / "prd_demo_0001_01.png"
    existing.write_bytes(b"existing")
    catalog_path.write_text(
        json.dumps(
            {
                "metadata": {},
                "categories": [],
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
                        "price_cents": 100,
                        "currency": "BRL",
                        "stock_quantity": 1,
                        "rating": 4.5,
                        "thumbnail": "/market/assets/catalog/prd_demo_0001.svg",
                        "images": ["/market/assets/catalog/prd_demo_0001.svg"],
                        "is_demo": True,
                        "status": "active",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = complete_catalog_images(
        catalog_path=catalog_path,
        output_path=catalog_path,
        assets_dir=assets_dir,
        model_dir=tmp_path / "model",
        seed=426,
        generator=FakeImageGenerator(),
    )

    assert summary.images_generated == 2
    assert existing.read_bytes() == b"existing"


def test_ecloe_market_blob_publisher_uploads_assets_and_rewrites_urls(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    output_path = tmp_path / "catalog.azure.json"
    assets_root = Path("src/demo/ecloe_market/assets/catalog")
    local_asset = assets_root / "prd_demo_test_01.png"
    full_asset = Path.cwd() / local_asset
    full_asset.parent.mkdir(parents=True, exist_ok=True)
    full_asset.write_bytes(b"png")
    catalog_path.write_text(
        json.dumps(
            {
                "metadata": {},
                "categories": [],
                "products": [
                    {
                        "product_id": "prd_demo_test",
                        "thumbnail": "/market/assets/catalog/prd_demo_test_01.png",
                        "images": ["/market/assets/catalog/prd_demo_test_01.png"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    client = FakeContainerClient()

    try:
        summary = publish_catalog_to_blob(
            catalog_path=catalog_path,
            output_path=output_path,
            account_url="https://acct.blob.core.windows.net",
            container_name="ecloe-market-demo-assets",
            blob_prefix="catalog",
            container_client=client,
        )
    finally:
        full_asset.unlink(missing_ok=True)

    rewritten = json.loads(output_path.read_text(encoding="utf-8"))
    image_url = "https://acct.blob.core.windows.net/ecloe-market-demo-assets/catalog/images/prd_demo_test_01.png"
    assert summary.images_uploaded == 1
    assert summary.catalog_blob == "catalog/catalog/catalog.azure.json"
    assert rewritten["products"][0]["thumbnail"] == image_url
    assert rewritten["products"][0]["images"] == [image_url]
    assert client.created is True
    assert client.blobs["catalog/images/prd_demo_test_01.png"].content == b"png"
    assert client.blobs["catalog/images/prd_demo_test_01.png"].content_type == "image/png"
    assert client.blobs["catalog/catalog/catalog.azure.json"].content_type == "application/json; charset=utf-8"


def test_ecloe_market_space_generator_calls_gradio_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_image = tmp_path / "space-output.png"
    source_image.write_bytes(b"space-png")
    calls = []

    class FakeClient:
        def __init__(self, space: str) -> None:
            self.space = space

        def predict(self, **kwargs):
            calls.append((self.space, kwargs))
            return str(source_image)

    monkeypatch.setitem(
        sys.modules,
        "gradio_client",
        types.SimpleNamespace(Client=FakeClient),
    )
    output_path = tmp_path / "catalog-image.png"

    generator = HuggingFaceSpaceImageGenerator("GuilhermeL/ecloe-hunyuan-image-3-demo", api_name="/generate")
    generator.generate("demo prompt", output_path, seed=426)

    assert output_path.read_bytes() == b"space-png"
    assert calls == [
        (
            "GuilhermeL/ecloe-hunyuan-image-3-demo",
            {"prompt": "demo prompt", "seed": 426, "api_name": "/generate"},
        )
    ]


class FakeImageGenerator:
    def generate(self, prompt: str, output_path: Path, *, seed: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"{seed}:{prompt}".encode())


class FakeBlob:
    def __init__(self) -> None:
        self.content = b""
        self.content_type = ""

    def upload_blob(self, data: bytes, **kwargs) -> None:
        self.content = data
        self.content_type = kwargs["content_settings"].content_type


class FakeContainerClient:
    def __init__(self) -> None:
        self.created = False
        self.blobs: dict[str, FakeBlob] = {}

    def create_container(self) -> None:
        self.created = True

    def get_blob_client(self, blob_name: str) -> FakeBlob:
        return self.blobs.setdefault(blob_name, FakeBlob())
