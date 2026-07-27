from __future__ import annotations

import argparse
import json
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.config import load_settings
from src.evaluation.validate_artifacts import DEFAULT_ARTIFACT_DIR, validate_artifacts


def publish_artifacts(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    promote: bool = False,
    run_id: str | None = None,
    allow_connection_string: bool = False,
) -> dict[str, Any]:
    settings = load_settings()
    if settings.azure_storage_connection_string and not allow_connection_string:
        raise RuntimeError(
            "AZURE_STORAGE_CONNECTION_STRING is for local development only. "
            "Pass --allow-connection-string only outside cloud runtime."
        )

    manifest = validate_artifacts(
        artifact_dir=artifact_dir,
        manifest_file=artifact_dir / "artifact_manifest.json",
        run_id=run_id,
        seed=settings.random_seed,
    )
    container = _artifact_container(settings)
    _ensure_container(container)

    effective_run_id = str(manifest["run_id"])
    uploaded: list[str] = []
    manifest_source = artifact_dir / "artifact_manifest.json"
    manifest_blob = f"runs/{effective_run_id}/artifact_manifest.json"
    _upload_blob(container, manifest_blob, manifest_source, overwrite=False)
    if _sha256_bytes(container.download_blob(manifest_blob).readall()) != _sha256_bytes(
        manifest_source.read_bytes()
    ):
        raise RuntimeError(f"Uploaded checksum mismatch for {manifest_blob}.")
    uploaded.append(manifest_blob)

    for artifact_name, artifact_info in manifest["artifacts"].items():
        source = artifact_dir / artifact_name
        if not source.exists() and artifact_name == "data_validation.json":
            source = settings.reports_dir / "data_validation.json"
        blob_name = f"runs/{effective_run_id}/{artifact_name}"
        _upload_blob(container, blob_name, source, overwrite=False)
        downloaded = container.download_blob(blob_name).readall()
        remote_sha256 = _sha256_bytes(downloaded)
        if remote_sha256 != artifact_info["sha256"]:
            raise RuntimeError(f"Uploaded checksum mismatch for {blob_name}.")
        uploaded.append(blob_name)

    promoted_blob = None
    if promote:
        promoted_blob = settings.azure_artifact_promotion_blob
        pointer = {
            "run_id": effective_run_id,
            "manifest_blob": f"runs/{effective_run_id}/artifact_manifest.json",
            "promoted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        container.upload_blob(
            promoted_blob,
            json.dumps(pointer, indent=2).encode("utf-8"),
            overwrite=True,
            content_settings=_content_settings("current.json"),
        )

    return {
        "run_id": effective_run_id,
        "container": settings.azure_blob_container_artifacts,
        "uploaded": uploaded,
        "promoted_blob": promoted_blob,
    }


def _artifact_container(settings):
    try:
        from azure.storage.blob import BlobServiceClient
    except ModuleNotFoundError as error:
        raise RuntimeError("azure-storage-blob is required to publish artifacts.") from error

    if settings.azure_storage_connection_string:
        service = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    else:
        if not settings.azure_storage_account_url:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT_URL is required to publish artifacts.")
        try:
            from azure.identity import DefaultAzureCredential
        except ModuleNotFoundError as error:
            raise RuntimeError("azure-identity is required to publish artifacts.") from error
        service = BlobServiceClient(
            account_url=settings.azure_storage_account_url,
            credential=DefaultAzureCredential(),
        )
    return service.get_container_client(settings.azure_blob_container_artifacts)


def _ensure_container(container) -> None:
    try:
        container.create_container()
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        error_code = getattr(error, "error_code", "")
        if status_code != 409 and error_code != "ContainerAlreadyExists":
            raise


def _upload_blob(container, blob_name: str, source: Path, *, overwrite: bool) -> None:
    try:
        container.upload_blob(
            blob_name,
            source.read_bytes(),
            overwrite=overwrite,
            content_settings=_content_settings(source.name),
        )
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        error_code = getattr(error, "error_code", "")
        if status_code != 409 and error_code not in {"BlobAlreadyExists", "ResourceExists"}:
            raise


def _content_settings(name: str):
    try:
        from azure.storage.blob import ContentSettings
    except ModuleNotFoundError:
        return None
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if name.endswith(".json"):
        content_type = "application/json"
    if name.endswith(".csv"):
        content_type = "text/csv"
    return ContentSettings(content_type=content_type)


def _sha256_bytes(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish validated ECloe artifacts to Azure Blob Storage.")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--allow-connection-string", action="store_true")
    args = parser.parse_args()

    result = publish_artifacts(
        artifact_dir=args.artifact_dir,
        promote=args.promote,
        run_id=args.run_id,
        allow_connection_string=args.allow_connection_string,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
