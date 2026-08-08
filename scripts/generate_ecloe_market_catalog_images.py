from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.core.config import load_settings

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS_DIR = ROOT_DIR / "src" / "demo" / "ecloe_market" / "assets" / "catalog"
MARKET_ASSET_PREFIX = "/market/assets/catalog/"
TARGET_IMAGE_COUNT = 3


class ImageGenerator(Protocol):
    def generate(self, prompt: str, output_path: Path, *, seed: int) -> None:
        ...


@dataclass(frozen=True)
class ImageCompletionSummary:
    products_updated: int
    images_generated: int
    output: Path


class HunyuanImageGenerator:
    def __init__(self, model_dir: Path) -> None:
        if not model_dir.exists():
            raise RuntimeError(
                "HunyuanImage model directory was not found. Download "
                "tencent/HunyuanImage-3.0 outside the normal app install and set "
                "ECLOE_MARKET_IMAGE_MODEL_DIR, for example data/external/HunyuanImage-3."
            )
        try:
            from transformers import AutoModelForCausalLM
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "transformers and the HunyuanImage GPU/image stack are required only for "
                "this opt-in generator. Install them outside the normal app dependencies."
            ) from error

        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_dir),
            trust_remote_code=True,
            device_map="auto",
        )
        load_tokenizer = getattr(self.model, "load_tokenizer", None)
        if callable(load_tokenizer):
            load_tokenizer(str(model_dir))

    def generate(self, prompt: str, output_path: Path, *, seed: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        for method_name in ("generate_image", "text_to_image", "infer"):
            method = getattr(self.model, method_name, None)
            if callable(method):
                result = method(prompt=prompt, seed=seed)
                _save_model_result(result, output_path)
                return
        raise RuntimeError(
            "Loaded HunyuanImage model does not expose a supported image-generation method. "
            "Use the repository's current inference wrapper or update this adapter."
        )


class HuggingFaceSpaceImageGenerator:
    def __init__(self, space: str, *, api_name: str, extra_kwargs: dict[str, Any] | None = None) -> None:
        if not space:
            raise RuntimeError("ECLOE_MARKET_IMAGE_SPACE is required when image backend is 'space'.")
        try:
            from gradio_client import Client
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "gradio_client is required for ECLOE_MARKET_IMAGE_BACKEND=space. "
                "Install the optional Space client dependency before generation."
            ) from error
        self.client = Client(space)
        self.api_name = api_name
        self.extra_kwargs = extra_kwargs or {}

    def generate(self, prompt: str, output_path: Path, *, seed: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.client.predict(
            prompt=prompt,
            seed=seed,
            **self.extra_kwargs,
            api_name=self.api_name,
        )
        _save_space_result(result, output_path)


def _save_model_result(result: Any, output_path: Path) -> None:
    image = result[0] if isinstance(result, (list, tuple)) and result else result
    save = getattr(image, "save", None)
    if callable(save):
        save(output_path)
        return
    if isinstance(image, bytes):
        output_path.write_bytes(image)
        return
    raise RuntimeError("HunyuanImage generation returned an unsupported image result.")


def _save_space_result(result: Any, output_path: Path) -> None:
    candidate = result[0] if isinstance(result, (list, tuple)) and result else result
    if isinstance(candidate, dict):
        candidate = candidate.get("path") or candidate.get("name") or candidate.get("url")
    if isinstance(candidate, str):
        if candidate.startswith(("http://", "https://")):
            _download_url(candidate, output_path)
        else:
            shutil.copy2(candidate, output_path)
        return
    _save_model_result(candidate, output_path)


def _download_url(url: str, output_path: Path) -> None:
    import urllib.request

    with urllib.request.urlopen(url, timeout=120) as response:
        output_path.write_bytes(response.read())


def build_image_generator(
    *,
    backend: str,
    model_dir: Path,
    space: str,
    space_api_name: str,
    space_extra_kwargs: dict[str, Any] | None = None,
) -> ImageGenerator:
    if backend == "local":
        return HunyuanImageGenerator(model_dir)
    if backend == "space":
        return HuggingFaceSpaceImageGenerator(
            space,
            api_name=space_api_name,
            extra_kwargs=space_extra_kwargs,
        )
    raise RuntimeError("ECLOE_MARKET_IMAGE_BACKEND must be either 'local' or 'space'.")


def complete_catalog_images(
    *,
    catalog_path: Path,
    output_path: Path,
    assets_dir: Path,
    model_dir: Path,
    seed: int,
    generator: ImageGenerator | None = None,
    backend: str = "local",
    space: str = "",
    space_api_name: str = "/generate",
    space_extra_kwargs: dict[str, Any] | None = None,
) -> ImageCompletionSummary:
    payload = _read_catalog(catalog_path)
    image_generator = generator or build_image_generator(
        backend=backend,
        model_dir=model_dir,
        space=space,
        space_api_name=space_api_name,
        space_extra_kwargs=space_extra_kwargs,
    )
    products_updated = 0
    images_generated = 0
    assets_dir.mkdir(parents=True, exist_ok=True)

    for index, product in enumerate(payload.get("products", []), start=1):
        product_id = str(product["product_id"])
        current_images = _usable_images(product.get("images", []))
        if len(current_images) >= TARGET_IMAGE_COUNT and not _uses_fallback_svg(current_images):
            product["images"] = current_images[:TARGET_IMAGE_COUNT]
            product["thumbnail"] = product["images"][0]
            continue

        generated_images = []
        for image_number in range(1, TARGET_IMAGE_COUNT + 1):
            asset_name = f"{product_id}_{image_number:02d}.png"
            output_image = assets_dir / asset_name
            image_url = f"{MARKET_ASSET_PREFIX}{asset_name}"
            if not output_image.exists():
                prompt = _product_prompt(product, variant=image_number)
                image_generator.generate(prompt, output_image, seed=seed + index * 10 + image_number)
                images_generated += 1
            generated_images.append(image_url)

        product["thumbnail"] = generated_images[0]
        product["images"] = generated_images
        products_updated += 1

    payload.setdefault("metadata", {})["image_generation"] = {
        "provider": "tencent/HunyuanImage-3.0",
        "target_images_per_product": TARGET_IMAGE_COUNT,
        "seed": seed,
        "notice": "Synthetic demo product images generated by an opt-in offline workflow.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ImageCompletionSummary(
        products_updated=products_updated,
        images_generated=images_generated,
        output=output_path,
    )


def _read_catalog(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _usable_images(raw_images: Any) -> list[str]:
    if not isinstance(raw_images, list):
        return []
    return [str(image) for image in raw_images if isinstance(image, str) and image.strip()]


def _uses_fallback_svg(images: list[str]) -> bool:
    return any(image.lower().endswith(".svg") for image in images)


def _product_prompt(product: dict[str, Any], *, variant: int) -> str:
    return (
        "Demo-safe ecommerce product photo, isolated marketplace catalog asset, "
        f"product: {product.get('title_en', product.get('title_pt', 'ECloe product'))}, "
        f"category: {product.get('category_id', 'marketplace')}, "
        f"brand: {product.get('brand', 'ECloe')}, "
        f"visual variation {variant}, clean studio lighting, no text, no logos, square image."
    )


def _parse_space_extra_kwargs(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError("ECLOE_MARKET_IMAGE_SPACE_EXTRA_KWARGS must be a JSON object.") from error
    if not isinstance(payload, dict):
        raise RuntimeError("ECLOE_MARKET_IMAGE_SPACE_EXTRA_KWARGS must be a JSON object.")
    return payload


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Complete ECloe Market catalog images with HunyuanImage.")
    parser.add_argument("--catalog", type=Path, default=settings.ecloe_market_catalog_path)
    parser.add_argument("--output", type=Path, default=settings.ecloe_market_catalog_path)
    parser.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS_DIR)
    parser.add_argument("--model-dir", type=Path, default=settings.ecloe_market_image_model_dir)
    parser.add_argument(
        "--backend",
        choices=("local", "space"),
        default=settings.ecloe_market_image_backend,
    )
    parser.add_argument("--space", default=settings.ecloe_market_image_space)
    parser.add_argument("--space-api-name", default=settings.ecloe_market_image_space_api_name)
    parser.add_argument(
        "--space-extra-kwargs",
        default=settings.ecloe_market_image_space_extra_kwargs,
        help="JSON object with additional Gradio endpoint parameters.",
    )
    parser.add_argument("--seed", type=int, default=settings.ecloe_market_catalog_seed)
    args = parser.parse_args()

    try:
        summary = complete_catalog_images(
            catalog_path=args.catalog,
            output_path=args.output,
            assets_dir=args.assets_dir,
            model_dir=args.model_dir,
            seed=args.seed,
            backend=args.backend,
            space=args.space,
            space_api_name=args.space_api_name,
            space_extra_kwargs=_parse_space_extra_kwargs(args.space_extra_kwargs),
        )
    except RuntimeError as error:
        print(f"ECloe Market image generation failed: {error}", file=sys.stderr)
        return 1

    print(
        "ECloe Market catalog images completed: "
        f"products_updated={summary.products_updated}; "
        f"images_generated={summary.images_generated}; "
        f"output={summary.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
