from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from scripts.generate_ecloe_market_catalog_images import (
    HuggingFaceSpaceImageGenerator,
    ZImageTurboLocalGenerator,
    _parse_space_extra_kwargs,
    _save_space_result,
    build_image_generator,
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
    existing.write_bytes(b"\x89PNG\r\n\x1a\nexisting")
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
    assert existing.read_bytes() == b"\x89PNG\r\n\x1a\nexisting"


def test_ecloe_market_image_completion_force_regenerates_existing_files(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    images = []
    for image_number in range(1, 4):
        asset_name = f"prd_demo_0001_{image_number:02d}.png"
        (assets_dir / asset_name).write_bytes(b"\x89PNG\r\n\x1a\nexisting")
        images.append(f"/market/assets/catalog/{asset_name}")
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
                        "thumbnail": images[0],
                        "images": images,
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
        force=True,
    )

    assert summary.products_updated == 1
    assert summary.images_generated == 3
    assert (assets_dir / "prd_demo_0001_01.png").read_bytes().startswith(b"437:")


def test_ecloe_market_image_completion_regenerates_invalid_png_files(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    invalid = assets_dir / "prd_demo_0001_01.png"
    invalid.write_bytes(b"RIFF-invalid-webp")
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

    assert summary.images_generated == 3
    assert invalid.read_bytes().startswith(b"437:")


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
    result_resolved = False

    class FakeJob:
        def result(self):
            nonlocal result_resolved
            result_resolved = True
            return (str(source_image), 426.0)

    class FakeClient:
        def __init__(self, space: str) -> None:
            self.space = space

        def submit(self, **kwargs):
            calls.append((self.space, kwargs))
            return FakeJob()

        def predict(self, **kwargs):
            raise AssertionError("Space generator should use submit().result() by default.")

    monkeypatch.setitem(
        sys.modules,
        "gradio_client",
        types.SimpleNamespace(Client=FakeClient),
    )
    output_path = tmp_path / "catalog-image.png"

    generator = HuggingFaceSpaceImageGenerator(
        "mrfakename/Z-Image-Turbo",
        api_name="/generate_image",
        extra_kwargs={
            "height": 1024,
            "width": 1024,
            "num_inference_steps": 9,
            "randomize_seed": False,
        },
    )
    generator.generate("demo prompt", output_path, seed=426)

    assert output_path.read_bytes() == b"space-png"
    assert result_resolved is True
    assert calls == [
        (
            "mrfakename/Z-Image-Turbo",
            {
                "prompt": "demo prompt",
                "seed": 426,
                "height": 1024,
                "width": 1024,
                "num_inference_steps": 9,
                "randomize_seed": False,
                "api_name": "/generate_image",
            },
        )
    ]


def test_ecloe_market_space_generator_can_fallback_to_predict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    generator = HuggingFaceSpaceImageGenerator(
        "mrfakename/Z-Image-Turbo",
        api_name="/generate_image",
        extra_kwargs={"height": 1024, "width": 1024, "num_inference_steps": 9, "randomize_seed": False},
        use_queue=False,
    )
    generator.generate("demo prompt", output_path, seed=426)

    assert output_path.read_bytes() == b"space-png"
    assert calls[0][0] == "mrfakename/Z-Image-Turbo"


def test_ecloe_market_space_result_saves_dict_path(tmp_path: Path) -> None:
    source_image = tmp_path / "space-output.png"
    source_image.write_bytes(b"space-png")
    output_path = tmp_path / "catalog-image.png"

    _save_space_result({"path": str(source_image)}, output_path)

    assert output_path.read_bytes() == b"space-png"


def test_ecloe_market_space_result_saves_object_path(tmp_path: Path) -> None:
    source_image = tmp_path / "space-output.png"
    source_image.write_bytes(b"space-png")
    output_path = tmp_path / "catalog-image.png"

    _save_space_result(types.SimpleNamespace(path=str(source_image)), output_path)

    assert output_path.read_bytes() == b"space-png"


def test_ecloe_market_space_result_downloads_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.generate_ecloe_market_catalog_images as image_generation

    downloads = []
    output_path = tmp_path / "catalog-image.png"

    def fake_download_url(url: str, path: Path) -> None:
        downloads.append((url, path))
        path.write_bytes(b"downloaded-png")

    monkeypatch.setattr(image_generation, "_download_url", fake_download_url)

    _save_space_result({"url": "https://example.test/image.png"}, output_path)

    assert output_path.read_bytes() == b"downloaded-png"
    assert downloads == [("https://example.test/image.png", output_path)]


def test_ecloe_market_space_extra_kwargs_accepts_json_string() -> None:
    payload = _parse_space_extra_kwargs(
        '"{\\"height\\":1024,\\"width\\":1024,\\"num_inference_steps\\":9,\\"randomize_seed\\":false}"'
    )

    assert payload == {
        "height": 1024,
        "width": 1024,
        "num_inference_steps": 9,
        "randomize_seed": False,
    }


def test_ecloe_market_space_extra_kwargs_accepts_powershell_unquoted_keys() -> None:
    payload = _parse_space_extra_kwargs(
        "{height:1024,width:1024,num_inference_steps:9,randomize_seed:false}"
    )

    assert payload == {
        "height": 1024,
        "width": 1024,
        "num_inference_steps": 9,
        "randomize_seed": False,
    }


def test_ecloe_market_zimage_local_generator_calls_diffusers_pipeline(tmp_path: Path) -> None:
    calls = {}
    pipeline_factory = FakeZImagePipelineFactory(calls)
    torch_module = FakeTorch(cuda_available=True)
    output_path = tmp_path / "catalog-image.png"

    generator = ZImageTurboLocalGenerator(
        model_id_or_path="Tongyi-MAI/Z-Image-Turbo",
        height=1024,
        width=1024,
        num_inference_steps=9,
        offload_mode="model",
        pipeline_factory=pipeline_factory,
        torch_module=torch_module,
    )
    generator.generate("demo prompt", output_path, seed=426)

    assert output_path.read_bytes() == b"zimage-png"
    assert calls["from_pretrained"] == {
        "model": "Tongyi-MAI/Z-Image-Turbo",
        "torch_dtype": "bfloat16",
    }
    assert calls["offload"] == "model"
    assert calls["pipeline"] == {
        "prompt": "demo prompt",
        "height": 1024,
        "width": 1024,
        "num_inference_steps": 9,
        "guidance_scale": 0.0,
        "generator": {"device": "cuda", "seed": 426},
    }


def test_ecloe_market_zimage_local_generator_requires_cuda(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="requires a CUDA-capable NVIDIA GPU"):
        ZImageTurboLocalGenerator(
            model_id_or_path="Tongyi-MAI/Z-Image-Turbo",
        height=1024,
        width=1024,
        num_inference_steps=9,
        offload_mode="model",
        pipeline_factory=FakeZImagePipelineFactory({}),
        torch_module=FakeTorch(cuda_available=False),
    )


def test_ecloe_market_build_image_generator_supports_zimage_local() -> None:
    with pytest.raises(RuntimeError, match=r"torch is required|CUDA-capable"):
        build_image_generator(
            backend="zimage-local",
            model_dir=Path("unused"),
            space="",
            space_api_name="",
            zimage_model="Tongyi-MAI/Z-Image-Turbo",
            image_height=1024,
            image_width=1024,
            image_steps=9,
            offload_mode="model",
        )


def test_ecloe_market_zimage_local_generator_can_disable_offload(tmp_path: Path) -> None:
    calls = {}
    torch_module = FakeTorch(cuda_available=True)
    generator = ZImageTurboLocalGenerator(
        model_id_or_path="Tongyi-MAI/Z-Image-Turbo",
        height=768,
        width=768,
        num_inference_steps=8,
        offload_mode="none",
        pipeline_factory=FakeZImagePipelineFactory(calls),
        torch_module=torch_module,
    )

    generator.generate("demo prompt", tmp_path / "catalog-image.png", seed=426)

    assert calls["from_pretrained"] == {
        "model": "Tongyi-MAI/Z-Image-Turbo",
        "torch_dtype": "bfloat16",
        "device_map": "cuda",
    }
    assert "offload" not in calls
    assert torch_module.calls["empty_cache_called"] is True


def test_ecloe_market_zimage_local_generator_can_use_sequential_offload(tmp_path: Path) -> None:
    calls = {}
    generator = ZImageTurboLocalGenerator(
        model_id_or_path="Tongyi-MAI/Z-Image-Turbo",
        height=768,
        width=768,
        num_inference_steps=8,
        offload_mode="sequential",
        pipeline_factory=FakeZImagePipelineFactory(calls),
        torch_module=FakeTorch(cuda_available=True),
    )

    generator.generate("demo prompt", tmp_path / "catalog-image.png", seed=426)

    assert calls["from_pretrained"] == {
        "model": "Tongyi-MAI/Z-Image-Turbo",
        "torch_dtype": "bfloat16",
    }
    assert calls["offload"] == "sequential"


class FakeImageGenerator:
    def generate(self, prompt: str, output_path: Path, *, seed: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"{seed}:{prompt}".encode())


class FakeTorchCuda:
    def __init__(self, *, available: bool, calls: dict) -> None:
        self.available = available
        self.calls = calls

    def is_available(self) -> bool:
        return self.available

    def empty_cache(self) -> None:
        self.calls["empty_cache_called"] = True


class FakeTorchGenerator:
    def __init__(self, device: str) -> None:
        self.payload = {"device": device, "seed": None}

    def manual_seed(self, seed: int) -> dict[str, int | str | None]:
        self.payload["seed"] = seed
        return self.payload


class FakeTorch:
    bfloat16 = "bfloat16"

    def __init__(self, *, cuda_available: bool) -> None:
        self.calls: dict = {}
        self.cuda = FakeTorchCuda(available=cuda_available, calls=self.calls)

    def Generator(self, device: str) -> FakeTorchGenerator:
        return FakeTorchGenerator(device)


class FakeZImage:
    def save(self, path: Path) -> None:
        path.write_bytes(b"zimage-png")


class FakeZImageResult:
    def __init__(self) -> None:
        self.images = [FakeZImage()]


class FakeZImagePipeline:
    def __init__(self, calls: dict) -> None:
        self.calls = calls

    def __call__(self, **kwargs) -> FakeZImageResult:
        self.calls["pipeline"] = kwargs
        return FakeZImageResult()

    def enable_model_cpu_offload(self) -> None:
        self.calls["offload"] = "model"

    def enable_sequential_cpu_offload(self) -> None:
        self.calls["offload"] = "sequential"


class FakeZImagePipelineFactory:
    def __init__(self, calls: dict) -> None:
        self.calls = calls

    def from_pretrained(self, model_id_or_path: str, **kwargs) -> FakeZImagePipeline:
        self.calls["from_pretrained"] = {
            "model": model_id_or_path,
            **kwargs,
        }
        return FakeZImagePipeline(self.calls)


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
