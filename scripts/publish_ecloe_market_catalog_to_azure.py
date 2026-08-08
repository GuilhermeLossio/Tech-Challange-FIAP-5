from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR, load_settings

MARKET_ASSET_PREFIX = "/market/assets/catalog/"


@dataclass(frozen=True)
class BlobPublishSummary:
    images_uploaded: int
    catalog_blob: str
    output: Path


@dataclass(frozen=True)
class BlobContentSettings:
    content_type: str


def publish_catalog_to_blob(
    *,
    catalog_path: Path,
    output_path: Path,
    account_url: str,
    container_name: str,
    blob_prefix: str,
    container_client: Any | None = None,
) -> BlobPublishSummary:
    if not account_url:
        raise RuntimeError("AZURE_STORAGE_ACCOUNT_URL is required to publish ECloe Market catalog assets.")
    payload = _read_catalog(catalog_path)
    prefix = blob_prefix.strip("/")
    client = container_client or _default_container_client(account_url, container_name)
    _create_container_if_needed(client)

    images_uploaded = 0
    for product in payload.get("products", []):
        rewritten_images = []
        for image_url in product.get("images", []):
            local_path = _local_asset_path(str(image_url))
            blob_name = _blob_name(prefix, "images", local_path.name)
            _upload_file(client, local_path, blob_name)
            rewritten_images.append(_blob_url(account_url, container_name, blob_name))
            images_uploaded += 1
        if rewritten_images:
            product["images"] = rewritten_images
            product["thumbnail"] = rewritten_images[0]

    payload.setdefault("metadata", {})["azure_blob"] = {
        "account_url": account_url.rstrip("/"),
        "container": container_name,
        "prefix": prefix,
    }
    catalog_blob = _blob_name(prefix, "catalog", output_path.name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    output_path.write_text(catalog_text, encoding="utf-8")
    _upload_bytes(
        client,
        catalog_text.encode("utf-8"),
        catalog_blob,
        content_type="application/json; charset=utf-8",
    )
    return BlobPublishSummary(
        images_uploaded=images_uploaded,
        catalog_blob=catalog_blob,
        output=output_path,
    )


def _default_container_client(account_url: str, container_name: str) -> Any:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ModuleNotFoundError as error:
        raise RuntimeError("Install the azure optional dependencies to publish Market assets.") from error

    service_client = BlobServiceClient(
        account_url=account_url.rstrip("/"),
        credential=DefaultAzureCredential(),
    )
    return service_client.get_container_client(container_name)


def _create_container_if_needed(container_client: Any) -> None:
    try:
        container_client.create_container()
    except Exception as error:
        if "ContainerAlreadyExists" not in error.__class__.__name__:
            message = str(error)
            if "ContainerAlreadyExists" not in message and "already exists" not in message.lower():
                raise


def _read_catalog(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _local_asset_path(image_url: str) -> Path:
    if image_url.startswith("https://"):
        raise RuntimeError(f"Image is already remote and cannot be uploaded from disk: {image_url}")
    if not image_url.startswith(MARKET_ASSET_PREFIX):
        raise RuntimeError(f"Unsupported ECloe Market image path: {image_url}")
    path = ROOT_DIR / "src" / "demo" / "ecloe_market" / "assets" / "catalog" / image_url.removeprefix(
        MARKET_ASSET_PREFIX
    )
    if not path.exists():
        raise RuntimeError(f"Catalog image file was not found: {path}")
    return path


def _blob_name(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part.strip("/"))


def _upload_file(container_client: Any, source: Path, blob_name: str) -> None:
    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    _upload_bytes(container_client, source.read_bytes(), blob_name, content_type=content_type)


def _upload_bytes(container_client: Any, data: bytes, blob_name: str, *, content_type: str) -> None:
    kwargs = {"overwrite": True}
    try:
        from azure.storage.blob import ContentSettings
    except ModuleNotFoundError:
        ContentSettings = BlobContentSettings
    kwargs["content_settings"] = ContentSettings(content_type=content_type)
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(data, **kwargs)


def _blob_url(account_url: str, container_name: str, blob_name: str) -> str:
    return f"{account_url.rstrip('/')}/{container_name}/{blob_name}"


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Publish ECloe Market catalog JSON and images to Azure Blob.")
    parser.add_argument("--catalog", type=Path, default=settings.ecloe_market_catalog_path)
    parser.add_argument("--output", type=Path, default=settings.ecloe_market_catalog_azure_path)
    parser.add_argument("--account-url", default=settings.azure_storage_account_url)
    parser.add_argument("--container", default=settings.ecloe_market_blob_container)
    parser.add_argument("--prefix", default=settings.ecloe_market_blob_prefix)
    args = parser.parse_args()

    try:
        summary = publish_catalog_to_blob(
            catalog_path=args.catalog,
            output_path=args.output,
            account_url=args.account_url,
            container_name=args.container,
            blob_prefix=args.prefix,
        )
    except RuntimeError as error:
        print(f"ECloe Market Azure Blob publish failed: {error}", file=sys.stderr)
        return 1

    print(
        "ECloe Market catalog published to Azure Blob: "
        f"images_uploaded={summary.images_uploaded}; "
        f"catalog_blob={summary.catalog_blob}; "
        f"output={summary.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
