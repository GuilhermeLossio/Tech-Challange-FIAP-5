from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.config import Settings
from src.evaluation.validate_artifacts import REQUIRED_ARTIFACTS, sha256_file


class ArtifactSourceError(RuntimeError):
    pass


def resolve_artifact_directory(settings: Settings) -> Path:
    if settings.artifact_source == "file":
        from src.evaluation.run import DEFAULT_OUTPUT_DIR

        return DEFAULT_OUTPUT_DIR
    if settings.artifact_source == "azure_blob":
        return download_promoted_artifacts(settings)
    raise ArtifactSourceError(f"Unsupported ARTIFACT_SOURCE: {settings.artifact_source}")


def download_promoted_artifacts(settings: Settings) -> Path:
    container = _artifact_container(settings)
    promoted = _download_json_blob(container, settings.azure_artifact_promotion_blob)
    run_id = promoted.get("run_id")
    manifest_blob = promoted.get("manifest_blob")
    if not isinstance(run_id, str) or not run_id:
        raise ArtifactSourceError("Promoted artifact pointer is missing run_id.")
    if not isinstance(manifest_blob, str) or not manifest_blob:
        raise ArtifactSourceError("Promoted artifact pointer is missing manifest_blob.")

    run_dir = settings.artifact_cache_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "artifact_manifest.json"
    _download_blob(container, manifest_blob, manifest_path)
    manifest = _read_json(manifest_path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ArtifactSourceError("Artifact manifest is missing artifacts.")

    for artifact_name in REQUIRED_ARTIFACTS:
        artifact_info = artifacts.get(artifact_name)
        if not isinstance(artifact_info, dict):
            raise ArtifactSourceError(f"Artifact manifest is missing {artifact_name}.")
        expected_checksum = artifact_info.get("sha256")
        if not isinstance(expected_checksum, str) or len(expected_checksum) != 64:
            raise ArtifactSourceError(f"Artifact manifest has invalid checksum for {artifact_name}.")

        blob_name = f"runs/{run_id}/{artifact_name}"
        target = run_dir / artifact_name
        _download_blob(container, blob_name, target)
        actual_checksum = sha256_file(target)
        if actual_checksum != expected_checksum:
            raise ArtifactSourceError(
                f"Checksum mismatch for {artifact_name}: {actual_checksum} != {expected_checksum}"
            )

    return run_dir


def _artifact_container(settings: Settings) -> Any:
    try:
        from azure.storage.blob import BlobServiceClient
    except ModuleNotFoundError as error:
        raise ArtifactSourceError("azure-storage-blob is required for ARTIFACT_SOURCE=azure_blob.") from error

    if settings.azure_storage_connection_string:
        service = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    else:
        if not settings.azure_storage_account_url:
            raise ArtifactSourceError("AZURE_STORAGE_ACCOUNT_URL is required for azure_blob artifacts.")
        try:
            from azure.identity import DefaultAzureCredential
        except ModuleNotFoundError as error:
            raise ArtifactSourceError("azure-identity is required for Azure Blob Managed Identity.") from error
        service = BlobServiceClient(
            account_url=settings.azure_storage_account_url,
            credential=DefaultAzureCredential(),
        )
    return service.get_container_client(settings.azure_blob_container_artifacts)


def _download_json_blob(container: Any, blob_name: str) -> dict[str, Any]:
    payload = container.download_blob(blob_name).readall()
    try:
        value = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ArtifactSourceError(f"Blob is not valid JSON: {blob_name}") from error
    if not isinstance(value, dict):
        raise ArtifactSourceError(f"Blob must contain a JSON object: {blob_name}")
    return value


def _download_blob(container: Any, blob_name: str, target: Path) -> None:
    try:
        payload = container.download_blob(blob_name).readall()
    except Exception as error:
        raise ArtifactSourceError(f"Could not download artifact blob: {blob_name}") from error
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ArtifactSourceError(f"Artifact cache file is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ArtifactSourceError(f"Artifact cache file must be a JSON object: {path}")
    return value
