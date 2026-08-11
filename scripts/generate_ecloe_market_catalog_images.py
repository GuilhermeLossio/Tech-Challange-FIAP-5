from __future__ import annotations

import argparse
import gc
import hashlib
import json
import re
import shutil
import sys
import zlib
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
    def __init__(
        self,
        space: str,
        *,
        api_name: str,
        extra_kwargs: dict[str, Any] | None = None,
        use_queue: bool = True,
    ) -> None:
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
        self.use_queue = use_queue

    def generate(self, prompt: str, output_path: Path, *, seed: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        kwargs = {
            "prompt": prompt,
            "seed": seed,
            **self.extra_kwargs,
            "api_name": self.api_name,
        }
        submit = getattr(self.client, "submit", None)
        if self.use_queue and callable(submit):
            job = submit(**kwargs)
            result = job.result()
        else:
            result = self.client.predict(**kwargs)
        _save_space_result(result, output_path)


class ZImageTurboLocalGenerator:
    def __init__(
        self,
        *,
        model_id_or_path: str,
        height: int,
        width: int,
        num_inference_steps: int,
        offload_mode: str,
        pipeline_factory: Any | None = None,
        torch_module: Any | None = None,
    ) -> None:
        if not model_id_or_path:
            raise RuntimeError("ECLOE_MARKET_IMAGE_ZIMAGE_MODEL is required for zimage-local.")
        if torch_module is None:
            try:
                import torch
            except ModuleNotFoundError as error:
                raise RuntimeError(_zimage_dependency_error("torch")) from error
            torch_module = torch
        if pipeline_factory is None:
            try:
                from diffusers import DiffusionPipeline
            except ModuleNotFoundError as error:
                raise RuntimeError(_zimage_dependency_error("diffusers")) from error
            pipeline_factory = DiffusionPipeline

        self.torch = torch_module
        if not self.torch.cuda.is_available():
            raise RuntimeError(
                "ECLOE_MARKET_IMAGE_BACKEND=zimage-local requires a CUDA-capable NVIDIA GPU. "
                "Install a CUDA PyTorch build in the separate image-generation environment."
            )

        load_kwargs: dict[str, Any] = {"torch_dtype": self.torch.bfloat16}
        if offload_mode == "none":
            load_kwargs["device_map"] = "cuda"
        self.pipe = pipeline_factory.from_pretrained(model_id_or_path, **load_kwargs)
        if offload_mode == "model":
            self.pipe.enable_model_cpu_offload()
        elif offload_mode == "sequential":
            self.pipe.enable_sequential_cpu_offload()
        elif offload_mode == "none":
            pass
        else:
            raise RuntimeError("ECLOE_MARKET_IMAGE_OFFLOAD_MODE must be one of: model, sequential, none.")
        self.height = height
        self.width = width
        self.num_inference_steps = num_inference_steps
        self.offload_mode = offload_mode

    def generate(self, prompt: str, output_path: Path, *, seed: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            generator = self.torch.Generator("cuda").manual_seed(seed)
            result = self.pipe(
                prompt=prompt,
                height=self.height,
                width=self.width,
                num_inference_steps=self.num_inference_steps,
                guidance_scale=0.0,
                generator=generator,
            )
            _save_model_result(result.images[0], output_path)
        finally:
            gc.collect()
            empty_cache = getattr(self.torch.cuda, "empty_cache", None)
            if callable(empty_cache):
                empty_cache()


class CatalogPngImageGenerator:
    def generate(self, prompt: str, output_path: Path, *, seed: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        renderer = _CatalogPngRenderer(seed=seed, prompt=prompt)
        output_path.write_bytes(renderer.render())


def _save_model_result(result: Any, output_path: Path) -> None:
    image = result[0] if isinstance(result, (list, tuple)) and result else result
    save = getattr(image, "save", None)
    if callable(save):
        save(output_path)
        return
    if isinstance(image, bytes):
        output_path.write_bytes(image)
        return
    raise RuntimeError("Image generation returned an unsupported image result.")


def _save_space_result(result: Any, output_path: Path) -> None:
    candidate = _space_result_candidate(result)
    if isinstance(candidate, str):
        if candidate.startswith(("http://", "https://")):
            _download_url(candidate, output_path)
        else:
            shutil.copy2(candidate, output_path)
        return
    _save_model_result(candidate, output_path)


def _space_result_candidate(result: Any) -> Any:
    candidate = result[0] if isinstance(result, (list, tuple)) and result else result
    if isinstance(candidate, dict):
        return candidate.get("path") or candidate.get("name") or candidate.get("url") or candidate
    for attribute in ("path", "url", "orig_name"):
        value = getattr(candidate, attribute, None)
        if value:
            return str(value)
    return candidate


def _download_url(url: str, output_path: Path) -> None:
    import urllib.request

    with urllib.request.urlopen(url, timeout=120) as response:
        output_path.write_bytes(response.read())


def _zimage_dependency_error(package: str) -> str:
    return (
        f"{package} is required for ECLOE_MARKET_IMAGE_BACKEND=zimage-local. "
        "Install the local GPU image stack outside the normal app dependencies: "
        "torch with CUDA, diffusers, transformers, accelerate, and pillow."
        " The main repository venv is pinned to Python 3.14.6; use a separate "
        "Python 3.12 image-generation venv for CUDA PyTorch on Windows."
    )


def build_image_generator(
    *,
    backend: str,
    model_dir: Path,
    space: str,
    space_api_name: str,
    space_extra_kwargs: dict[str, Any] | None = None,
    zimage_model: str = "Tongyi-MAI/Z-Image-Turbo",
    image_height: int = 1024,
    image_width: int = 1024,
    image_steps: int = 9,
    offload_mode: str = "model",
) -> ImageGenerator:
    if backend in {"local", "hunyuan-local"}:
        return HunyuanImageGenerator(model_dir)
    if backend == "zimage-local":
        return ZImageTurboLocalGenerator(
            model_id_or_path=zimage_model,
            height=image_height,
            width=image_width,
            num_inference_steps=image_steps,
            offload_mode=offload_mode,
        )
    if backend == "space":
        return HuggingFaceSpaceImageGenerator(
            space,
            api_name=space_api_name,
            extra_kwargs=space_extra_kwargs,
        )
    if backend == "catalog":
        return CatalogPngImageGenerator()
    raise RuntimeError(
        "ECLOE_MARKET_IMAGE_BACKEND must be one of: zimage-local, space, local, hunyuan-local, catalog."
    )


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
    zimage_model: str = "Tongyi-MAI/Z-Image-Turbo",
    image_height: int = 1024,
    image_width: int = 1024,
    image_steps: int = 9,
    offload_mode: str = "model",
    force: bool = False,
) -> ImageCompletionSummary:
    payload = _read_catalog(catalog_path)
    image_generator = generator or build_image_generator(
        backend=backend,
        model_dir=model_dir,
        space=space,
        space_api_name=space_api_name,
        space_extra_kwargs=space_extra_kwargs,
        zimage_model=zimage_model,
        image_height=image_height,
        image_width=image_width,
        image_steps=image_steps,
        offload_mode=offload_mode,
    )
    products_updated = 0
    images_generated = 0
    assets_dir.mkdir(parents=True, exist_ok=True)

    for index, product in enumerate(payload.get("products", []), start=1):
        product_id = str(product["product_id"])
        current_images = _usable_images(product.get("images", []))
        if (
            not force
            and len(current_images) >= TARGET_IMAGE_COUNT
            and not _uses_fallback_svg(current_images)
            and _referenced_images_are_valid(current_images[:TARGET_IMAGE_COUNT], assets_dir)
        ):
            product["images"] = current_images[:TARGET_IMAGE_COUNT]
            product["thumbnail"] = product["images"][0]
            continue

        generated_images = []
        for image_number in range(1, TARGET_IMAGE_COUNT + 1):
            asset_name = f"{product_id}_{image_number:02d}.png"
            output_image = assets_dir / asset_name
            image_url = f"{MARKET_ASSET_PREFIX}{asset_name}"
            if force or not output_image.exists() or not _is_png_file(output_image):
                prompt = _product_prompt(product, variant=image_number)
                image_generator.generate(prompt, output_image, seed=seed + index * 10 + image_number)
                images_generated += 1
            generated_images.append(image_url)

        product["thumbnail"] = generated_images[0]
        product["images"] = generated_images
        products_updated += 1

    payload.setdefault("metadata", {})["image_generation"] = {
        "provider": _image_generation_provider(
            backend=backend,
            model_dir=model_dir,
            space=space,
            zimage_model=zimage_model,
        ),
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


def _referenced_images_are_valid(images: list[str], assets_dir: Path) -> bool:
    for image in images:
        if not image.startswith(MARKET_ASSET_PREFIX):
            return True
        path = assets_dir / image.removeprefix(MARKET_ASSET_PREFIX)
        if path.suffix.lower() == ".png" and not _is_png_file(path):
            return False
    return True


def _product_prompt(product: dict[str, Any], *, variant: int) -> str:
    return (
        "Demo-safe ecommerce product photo, isolated marketplace catalog asset, "
        f"product: {product.get('title_en', product.get('title_pt', 'ECloe product'))}, "
        f"category: {product.get('category_id', 'marketplace')}, "
        f"brand: {product.get('brand', 'ECloe')}, "
        f"visual variation {variant}, clean studio lighting, no text, no logos, square image."
    )


def _is_png_file(path: Path) -> bool:
    try:
        return path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False


def _image_generation_provider(*, backend: str, model_dir: Path, space: str, zimage_model: str) -> str:
    if backend == "zimage-local":
        return zimage_model
    if backend == "space":
        return space or "huggingface-space"
    if backend == "catalog":
        return "local-catalog-renderer"
    return f"tencent/HunyuanImage-3.0 ({model_dir.as_posix()})"


class _CatalogPngRenderer:
    width = 1024
    height = 1024

    def __init__(self, *, seed: int, prompt: str) -> None:
        self.seed = seed
        self.prompt = prompt
        digest = hashlib.sha256(f"{seed}:{prompt}".encode()).digest()
        self.primary = (40 + digest[0] % 155, 50 + digest[1] % 145, 60 + digest[2] % 135)
        self.secondary = (90 + digest[3] % 130, 80 + digest[4] % 130, 70 + digest[5] % 130)
        self.accent = (180 + digest[6] % 60, 135 + digest[7] % 90, 75 + digest[8] % 120)
        self.pixels = bytearray(self.width * self.height * 3)

    def render(self) -> bytes:
        self._background()
        self._shadow()
        category = self._category()
        if category == "cat_tech":
            self._draw_tech()
        elif category == "cat_beauty":
            self._draw_beauty()
        elif category == "cat_home":
            self._draw_home()
        elif category == "cat_style":
            self._draw_style()
        elif category == "cat_wellness":
            self._draw_wellness()
        elif category == "cat_grocery":
            self._draw_grocery()
        else:
            self._draw_box()
        self._draw_shelf()
        return self._png_bytes()

    def _category(self) -> str:
        marker = "category: "
        if marker not in self.prompt:
            return ""
        return self.prompt.split(marker, 1)[1].split(",", 1)[0].strip()

    def _background(self) -> None:
        for y in range(self.height):
            blend = y / (self.height - 1)
            color = (
                int(246 - blend * 18),
                int(247 - blend * 14),
                int(244 - blend * 10),
            )
            self._rect(0, y, self.width, y + 1, color)
        self._circle(180, 170, 120, self._mix(self.primary, (255, 255, 255), 0.78))
        self._circle(850, 210, 150, self._mix(self.secondary, (255, 255, 255), 0.82))

    def _shadow(self) -> None:
        self._ellipse(512, 758, 300, 52, (205, 207, 210))
        self._ellipse(512, 750, 240, 38, (188, 191, 195))

    def _draw_tech(self) -> None:
        self._rounded_rect(346, 210, 678, 712, 28, self.primary)
        self._rounded_rect(380, 252, 644, 650, 18, (236, 241, 245))
        self._rect(414, 304, 610, 432, self._mix(self.secondary, (255, 255, 255), 0.35))
        self._rect(414, 462, 610, 500, self.accent)
        self._circle(512, 682, 18, (230, 234, 238))

    def _draw_beauty(self) -> None:
        self._rounded_rect(392, 330, 632, 710, 34, self._mix(self.primary, (255, 255, 255), 0.18))
        self._rect(430, 282, 594, 350, self.secondary)
        self._rounded_rect(454, 226, 570, 290, 16, self.accent)
        self._rect(430, 482, 594, 570, (245, 238, 232))
        self._circle(512, 526, 42, self.accent)

    def _draw_home(self) -> None:
        self._rect(482, 318, 542, 716, self.primary)
        self._polygon([(320, 370), (704, 370), (626, 210), (398, 210)], self.secondary)
        self._rect(334, 696, 690, 746, self.accent)
        self._rect(366, 746, 418, 824, self.primary)
        self._rect(606, 746, 658, 824, self.primary)

    def _draw_style(self) -> None:
        self._polygon([(512, 210), (678, 310), (628, 688), (396, 688), (346, 310)], self.primary)
        self._polygon([(512, 210), (586, 282), (512, 350), (438, 282)], (244, 245, 247))
        self._rect(418, 430, 606, 482, self.accent)
        self._circle(440, 352, 18, self.secondary)
        self._circle(584, 352, 18, self.secondary)

    def _draw_wellness(self) -> None:
        self._circle(512, 500, 190, self._mix(self.primary, (255, 255, 255), 0.18))
        self._ellipse(430, 480, 72, 190, self.secondary)
        self._ellipse(584, 480, 72, 190, self.accent)
        self._rect(498, 300, 526, 702, (238, 241, 235))
        self._circle(512, 500, 56, (246, 248, 244))

    def _draw_grocery(self) -> None:
        self._rounded_rect(370, 292, 654, 724, 26, self.primary)
        self._rect(420, 228, 604, 314, self.secondary)
        self._rect(400, 448, 624, 570, (247, 244, 232))
        self._circle(512, 510, 48, self.accent)
        self._rect(438, 610, 586, 648, self.secondary)

    def _draw_box(self) -> None:
        self._polygon([(342, 360), (512, 260), (682, 360), (512, 460)], self.accent)
        self._polygon([(342, 360), (512, 460), (512, 740), (342, 620)], self.primary)
        self._polygon([(682, 360), (512, 460), (512, 740), (682, 620)], self.secondary)

    def _draw_shelf(self) -> None:
        self._rect(276, 790, 748, 818, (172, 176, 180))
        self._rect(324, 818, 700, 842, (128, 135, 142))

    def _rect(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.width, x1), min(self.height, y1)
        for y in range(y0, y1):
            row = (y * self.width + x0) * 3
            for _ in range(x0, x1):
                self.pixels[row : row + 3] = bytes(color)
                row += 3

    def _rounded_rect(
        self, x0: int, y0: int, x1: int, y1: int, radius: int, color: tuple[int, int, int]
    ) -> None:
        self._rect(x0 + radius, y0, x1 - radius, y1, color)
        self._rect(x0, y0 + radius, x1, y1 - radius, color)
        self._circle(x0 + radius, y0 + radius, radius, color)
        self._circle(x1 - radius - 1, y0 + radius, radius, color)
        self._circle(x0 + radius, y1 - radius - 1, radius, color)
        self._circle(x1 - radius - 1, y1 - radius - 1, radius, color)

    def _circle(self, cx: int, cy: int, radius: int, color: tuple[int, int, int]) -> None:
        r2 = radius * radius
        for y in range(max(0, cy - radius), min(self.height, cy + radius + 1)):
            for x in range(max(0, cx - radius), min(self.width, cx + radius + 1)):
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r2:
                    idx = (y * self.width + x) * 3
                    self.pixels[idx : idx + 3] = bytes(color)

    def _ellipse(self, cx: int, cy: int, rx: int, ry: int, color: tuple[int, int, int]) -> None:
        for y in range(max(0, cy - ry), min(self.height, cy + ry + 1)):
            for x in range(max(0, cx - rx), min(self.width, cx + rx + 1)):
                if ((x - cx) * (x - cx)) / (rx * rx) + ((y - cy) * (y - cy)) / (ry * ry) <= 1:
                    idx = (y * self.width + x) * 3
                    self.pixels[idx : idx + 3] = bytes(color)

    def _polygon(self, points: list[tuple[int, int]], color: tuple[int, int, int]) -> None:
        min_y = max(0, min(y for _, y in points))
        max_y = min(self.height - 1, max(y for _, y in points))
        for y in range(min_y, max_y + 1):
            intersections = []
            for i, (x1, y1) in enumerate(points):
                x2, y2 = points[(i + 1) % len(points)]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    intersections.append(int(x1 + (y - y1) * (x2 - x1) / (y2 - y1)))
            intersections.sort()
            for left, right in zip(intersections[0::2], intersections[1::2], strict=False):
                self._rect(left, y, right + 1, y + 1, color)

    def _mix(
        self,
        a: tuple[int, int, int],
        b: tuple[int, int, int],
        ratio: float,
    ) -> tuple[int, int, int]:
        return tuple(int(a[i] * (1 - ratio) + b[i] * ratio) for i in range(3))

    def _png_bytes(self) -> bytes:
        rows = bytearray()
        stride = self.width * 3
        for y in range(self.height):
            rows.append(0)
            start = y * stride
            rows.extend(self.pixels[start : start + stride])
        return (
            b"\x89PNG\r\n\x1a\n"
            + self._chunk(b"IHDR", self.width.to_bytes(4, "big") + self.height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00")
            + self._chunk(b"IDAT", zlib.compress(bytes(rows), level=6))
            + self._chunk(b"IEND", b"")
        )

    def _chunk(self, chunk_type: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return len(data).to_bytes(4, "big") + chunk_type + data + checksum.to_bytes(4, "big")


def _parse_space_extra_kwargs(raw: str) -> dict[str, Any]:
    value = raw or "{}"
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        payload = _parse_powershell_relaxed_json(value)
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = _parse_powershell_relaxed_json(payload)
    if not isinstance(payload, dict):
        raise RuntimeError("ECLOE_MARKET_IMAGE_SPACE_EXTRA_KWARGS must be a JSON object.")
    return payload


def _parse_powershell_relaxed_json(raw: str) -> Any:
    normalized = re.sub(r'([,{]\s*)([A-Za-z_][A-Za-z0-9_-]*)(\s*:)', r'\1"\2"\3', raw)
    try:
        return json.loads(normalized)
    except json.JSONDecodeError as error:
        raise RuntimeError("ECLOE_MARKET_IMAGE_SPACE_EXTRA_KWARGS must be a JSON object.") from error


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Complete ECloe Market catalog images.")
    parser.add_argument("--catalog", type=Path, default=settings.ecloe_market_catalog_path)
    parser.add_argument("--output", type=Path, default=settings.ecloe_market_catalog_path)
    parser.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS_DIR)
    parser.add_argument("--model-dir", type=Path, default=settings.ecloe_market_image_model_dir)
    parser.add_argument(
        "--backend",
        choices=("zimage-local", "space", "local", "hunyuan-local", "catalog"),
        default=settings.ecloe_market_image_backend,
    )
    parser.add_argument("--space", default=settings.ecloe_market_image_space)
    parser.add_argument("--space-api-name", default=settings.ecloe_market_image_space_api_name)
    parser.add_argument(
        "--space-extra-kwargs",
        default=settings.ecloe_market_image_space_extra_kwargs,
        help="JSON object with additional Gradio endpoint parameters.",
    )
    parser.add_argument("--zimage-model", default=settings.ecloe_market_image_zimage_model)
    parser.add_argument("--height", type=int, default=settings.ecloe_market_image_height)
    parser.add_argument("--width", type=int, default=settings.ecloe_market_image_width)
    parser.add_argument("--steps", type=int, default=settings.ecloe_market_image_steps)
    parser.add_argument(
        "--offload-mode",
        choices=("model", "sequential", "none"),
        default=settings.ecloe_market_image_offload_mode,
    )
    parser.add_argument("--seed", type=int, default=settings.ecloe_market_catalog_seed)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate all target catalog PNGs even when existing images are valid.",
    )
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
            zimage_model=args.zimage_model,
            image_height=args.height,
            image_width=args.width,
            image_steps=args.steps,
            offload_mode=args.offload_mode,
            force=args.force,
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
