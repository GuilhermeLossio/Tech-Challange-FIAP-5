from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.core.config import Settings, load_settings
from src.evaluation.run import DEFAULT_OUTPUT_DIR


TRAINING_RUN_POLICY_NAME = "__training_run__"


def build_training_result_documents(artifact_dir: Path = DEFAULT_OUTPUT_DIR) -> list[dict[str, Any]]:
    policy_versions = _read_json(artifact_dir / "policy_versions.json")
    selected_policy = _read_json(artifact_dir / "selected_policy.json")
    manifest = _read_json(artifact_dir / "artifact_manifest.json")

    if not isinstance(policy_versions, list):
        raise ValueError("policy_versions.json must contain a list.")
    if not isinstance(selected_policy, dict):
        raise ValueError("selected_policy.json must contain an object.")
    if not isinstance(manifest, dict):
        raise ValueError("artifact_manifest.json must contain an object.")

    run_id = str(manifest.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("artifact_manifest.json must include run_id.")

    documents: list[dict[str, Any]] = []
    for item in policy_versions:
        if not isinstance(item, dict):
            raise ValueError("Every policy_versions.json item must be an object.")
        policy_name = str(item.get("policy_name", "")).strip()
        version = str(item.get("version", "")).strip()
        if not policy_name or not version:
            raise ValueError("Each policy version must include policy_name and version.")

        documents.append(
            {
                **item,
                "id": f"{run_id}:{policy_name}:{version}",
                "record_type": "policy_version",
                "policy_name": policy_name,
                "run_id": run_id,
                "artifact_manifest": {
                    "run_id": run_id,
                    "git_commit": manifest.get("git_commit", ""),
                    "dataset_sha256": manifest.get("dataset_sha256", ""),
                    "python_version": manifest.get("python_version", ""),
                    "seed": manifest.get("seed"),
                    "generated_at": manifest.get("generated_at", ""),
                    "policy_versions_sha256": manifest.get("artifacts", {})
                    .get("policy_versions.json", {})
                    .get("sha256", ""),
                    "selected_policy_sha256": manifest.get("artifacts", {})
                    .get("selected_policy.json", {})
                    .get("sha256", ""),
                },
                "selected_offline_policy": selected_policy.get("policy", ""),
            }
        )

    documents.append(
        {
            "id": f"{run_id}:training_run",
            "record_type": "training_run",
            "policy_name": TRAINING_RUN_POLICY_NAME,
            "run_id": run_id,
            "status": "validated",
            "selected_offline_policy": selected_policy.get("policy", ""),
            "selected_policy": selected_policy,
            "manifest": manifest,
        }
    )
    return documents


def publish_training_results(
    *,
    artifact_dir: Path = DEFAULT_OUTPUT_DIR,
    settings: Settings | None = None,
) -> dict[str, Any]:
    effective_settings = settings or load_settings()
    documents = build_training_result_documents(artifact_dir)
    container = _policy_container(effective_settings)

    upserted = []
    for document in documents:
        container.upsert_item(document)
        upserted.append(document["id"])

    return {
        "cosmos_endpoint": effective_settings.azure_cosmos_endpoint,
        "database": effective_settings.azure_cosmos_database,
        "container": effective_settings.azure_cosmos_container_policies,
        "documents_upserted": len(upserted),
        "document_ids": upserted,
    }


def _policy_container(settings: Settings) -> Any:
    try:
        from azure.cosmos import CosmosClient
    except ModuleNotFoundError as error:
        raise RuntimeError("azure-cosmos is required to publish training results.") from error

    client = CosmosClient(settings.azure_cosmos_endpoint, credential=_cosmos_credential(settings))
    database = client.get_database_client(settings.azure_cosmos_database)
    return database.get_container_client(settings.azure_cosmos_container_policies)


def _cosmos_credential(settings: Settings) -> Any:
    if settings.azure_cosmos_auth_mode == "managed_identity":
        try:
            from azure.identity import DefaultAzureCredential
        except ModuleNotFoundError as error:
            raise RuntimeError("azure-identity is required for Cosmos DB Managed Identity.") from error
        return DefaultAzureCredential()

    if settings.azure_cosmos_key:
        return settings.azure_cosmos_key

    raise RuntimeError("Cosmos DB credential is not configured.")


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish validated ECloe training results to Cosmos DB policy_versions."
    )
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    result = publish_training_results(artifact_dir=args.artifact_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
