from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from src.core.config import Settings
from src.evaluation.validate_artifacts import REQUIRED_ARTIFACTS, sha256_file
from src.recommendation.artifacts import (
    RECOMMENDATION_ARTIFACT_SCHEMA,
    RecommendationArtifactMetadata,
    RecommendationRuntime,
    evidence_from_payload,
)
from src.recommendation.models import RecommendationEvidence, Surface

logger = logging.getLogger(__name__)


class ArtifactSourceError(RuntimeError):
    pass


RECOMMENDATION_ARTIFACTS = (
    "recommendation_evidence.json",
    "selected_policy.json",
    "metrics.json",
    "golden_set_recommendations.json",
    "artifact_manifest.json",
)


def resolve_artifact_directory(settings: Settings) -> Path:
    if settings.artifact_source == "file":
        from src.evaluation.run import DEFAULT_OUTPUT_DIR

        return DEFAULT_OUTPUT_DIR
    if settings.artifact_source == "azure_blob":
        return download_promoted_artifacts(settings)
    raise ArtifactSourceError(f"Unsupported ARTIFACT_SOURCE: {settings.artifact_source}")


def load_recommendation_runtimes(
    settings: Settings,
) -> dict[Surface, RecommendationRuntime]:
    runtimes: dict[Surface, RecommendationRuntime] = {}
    for surface in (Surface.market, Surface.pay):
        try:
            runtimes[surface] = load_recommendation_runtime(settings, surface)
        except (ArtifactSourceError, FileNotFoundError, ValueError) as error:
            logger.warning(
                "Recommendation artifact fallback surface=%s reason=%s",
                surface.value,
                type(error).__name__,
            )
            runtimes[surface] = RecommendationRuntime(
                evidence=RecommendationEvidence(),
                policy="deterministic_baseline",
                metadata=RecommendationArtifactMetadata(
                    surface=surface,
                    run_id="baseline",
                    version=f"{surface.value}-baseline-v1",
                    checksum=hashlib.sha256(f"{surface.value}:baseline".encode()).hexdigest(),
                    warning="artifact_fallback_baseline",
                ),
            )
    return runtimes


def load_recommendation_runtime(settings: Settings, surface: Surface) -> RecommendationRuntime:
    if settings.artifact_source == "file":
        directory = _local_recommendation_directory(settings, surface)
    elif settings.artifact_source == "azure_blob":
        directory = download_promoted_recommendation_artifacts(settings, surface)
    else:
        raise ArtifactSourceError(f"Unsupported ARTIFACT_SOURCE: {settings.artifact_source}")

    evidence = _read_json(directory / "recommendation_evidence.json")
    selected = _read_json(directory / "selected_policy.json")
    manifest = _read_json(directory / "artifact_manifest.json")
    if manifest.get("surface") != surface.value:
        raise ArtifactSourceError("Recommendation artifact surface does not match the runtime surface.")
    for name in RECOMMENDATION_ARTIFACTS:
        if name == "artifact_manifest.json":
            continue
        expected = manifest.get("artifacts", {}).get(name, {}).get("sha256")
        target = directory / name
        if not isinstance(expected, str) or len(expected) != 64 or not target.exists():
            raise ArtifactSourceError(f"Recommendation artifact checksum is missing for {name}.")
        if sha256_file(target) != expected:
            raise ArtifactSourceError(f"Recommendation artifact checksum mismatch for {name}.")
    if selected.get("artifact_status", "active") != "active":
        raise ArtifactSourceError("Selected recommendation policy is not active.")
    if selected.get("schema_version") != RECOMMENDATION_ARTIFACT_SCHEMA:
        raise ArtifactSourceError("Unsupported selected recommendation policy schema.")
    policy = selected.get("policy")
    version = selected.get("version")
    run_id = manifest.get("run_id")
    if not all(isinstance(value, str) and value for value in (policy, version, run_id)):
        raise ArtifactSourceError("Recommendation artifact metadata is incomplete.")
    checksum = manifest.get("artifacts", {}).get("recommendation_evidence.json", {}).get("sha256")
    if not isinstance(checksum, str) or len(checksum) != 64:
        raise ArtifactSourceError("Recommendation evidence checksum is missing.")
    return RecommendationRuntime(
        evidence=evidence_from_payload(evidence),
        policy=policy,
        metadata=RecommendationArtifactMetadata(
            surface=surface,
            run_id=run_id,
            version=version,
            checksum=checksum,
            path=str(directory),
        ),
    )


def download_promoted_recommendation_artifacts(settings: Settings, surface: Surface) -> Path:
    container = _artifact_container(settings)
    pointer_name = (
        settings.azure_artifact_promotion_blob_market
        if surface is Surface.market
        else settings.azure_artifact_promotion_blob_pay
    )
    legacy_pointer = False
    try:
        pointer = _download_json_blob(container, pointer_name)
    except Exception:
        legacy_pointer = True
        pointer = _download_json_blob(container, settings.azure_artifact_promotion_blob)
    run_id = pointer.get("run_id")
    manifest_blob = pointer.get("manifest_blob")
    if not isinstance(run_id, str) or not run_id or not isinstance(manifest_blob, str):
        raise ArtifactSourceError("Recommendation promotion pointer is invalid.")
    run_dir = settings.artifact_cache_dir / surface.value / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "artifact_manifest.json"
    _download_blob(container, manifest_blob, manifest_path)
    manifest = _read_json(manifest_path)
    if manifest.get("surface") != surface.value:
        raise ArtifactSourceError("Promoted recommendation manifest has the wrong surface.")
    for name in RECOMMENDATION_ARTIFACTS:
        if name == "artifact_manifest.json":
            continue
        info = manifest.get("artifacts", {}).get(name, {})
        expected = info.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            raise ArtifactSourceError(f"Manifest is missing checksum for {name}.")
        target = run_dir / name
        prefix = f"runs/{run_id}" if legacy_pointer else f"runs/{surface.value}/{run_id}"
        _download_blob(container, f"{prefix}/{name}", target)
        if sha256_file(target) != expected:
            raise ArtifactSourceError(f"Checksum mismatch for {name}.")
    return run_dir


def _local_recommendation_directory(settings: Settings, surface: Surface) -> Path:
    directory = settings.reports_dir / "recommendation" / surface.value
    if directory.exists():
        return directory
    raise FileNotFoundError(directory)


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
