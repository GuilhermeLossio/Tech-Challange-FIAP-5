from __future__ import annotations

import json
from dataclasses import replace

from src.core.config import load_settings
from src.engine.artifact_sources import download_promoted_artifacts, resolve_artifact_directory
from src.evaluation.validate_artifacts import REQUIRED_ARTIFACTS, sha256_file


class FakeDownload:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def readall(self) -> bytes:
        return self.payload


class FakeContainer:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs

    def download_blob(self, blob_name: str) -> FakeDownload:
        return FakeDownload(self.blobs[blob_name])


def test_resolve_artifact_directory_uses_file_default() -> None:
    settings = load_settings(use_env_file=False)

    artifact_dir = resolve_artifact_directory(settings)

    assert artifact_dir.name == "policy_training"


def test_download_promoted_artifacts_verifies_manifest(monkeypatch, tmp_path) -> None:
    run_id = "train-test"
    blobs: dict[str, bytes] = {}
    artifact_payloads: dict[str, bytes] = {}
    for name in REQUIRED_ARTIFACTS:
        path = tmp_path / name
        path.write_bytes(b"{}")
        artifact_payloads[name] = path.read_bytes()
    manifest = {
        "run_id": run_id,
        "artifacts": {
            name: {
                "sha256": sha256_file(tmp_path / name),
                "size": len(payload),
            }
            for name, payload in artifact_payloads.items()
        },
    }
    blobs["promoted/current.json"] = json.dumps(
        {
            "run_id": run_id,
            "manifest_blob": f"runs/{run_id}/artifact_manifest.json",
        }
    ).encode("utf-8")
    blobs[f"runs/{run_id}/artifact_manifest.json"] = json.dumps(manifest).encode("utf-8")
    for name, payload in artifact_payloads.items():
        blobs[f"runs/{run_id}/{name}"] = payload

    settings = replace(
        load_settings(use_env_file=False),
        artifact_source="azure_blob",
        artifact_cache_dir=tmp_path / "cache",
        azure_storage_account_url="https://example.blob.core.windows.net",
    )
    monkeypatch.setattr(
        "src.engine.artifact_sources._artifact_container",
        lambda _: FakeContainer(blobs),
    )

    artifact_dir = download_promoted_artifacts(settings)

    assert artifact_dir == tmp_path / "cache" / run_id
    assert (artifact_dir / "selected_policy.json").exists()
