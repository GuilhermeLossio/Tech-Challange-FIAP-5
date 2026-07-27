from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.bandits import ACTIONS
from src.engine.artifacts import (
    ARTIFACT_STATUS_ACTIVE,
    LIKELIHOOD_MODEL_SCHEMA,
    SELECTED_POLICY_SCHEMA,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = ROOT_DIR / "reports" / "policy_training"
DEFAULT_DATA_VALIDATION_FILE = ROOT_DIR / "reports" / "data_validation.json"
DEFAULT_DATASET_FILE = ROOT_DIR / "data" / "processed" / "hillstrom_processed.csv"
DEFAULT_MANIFEST_FILE = DEFAULT_ARTIFACT_DIR / "artifact_manifest.json"
REQUIRED_POLICIES = {"baseline", "epsilon_greedy", "ucb", "thompson_sampling"}
REQUIRED_ARTIFACTS = (
    "metrics.json",
    "metrics.csv",
    "policy_versions.json",
    "selected_policy.json",
    "golden_set_recommendations.json",
    "policy_state_thompson_sampling.json",
    "purchase_likelihood_model.json",
    "data_validation.json",
)
METRIC_FIELDS = (
    "rounds",
    "cumulative_reward",
    "conversion_rate",
    "cumulative_regret",
    "exploration_rate",
)


class ArtifactValidationFailure(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifacts(
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    *,
    data_validation_file: Path = DEFAULT_DATA_VALIDATION_FILE,
    dataset_file: Path = DEFAULT_DATASET_FILE,
    manifest_file: Path | None = DEFAULT_MANIFEST_FILE,
    seed: int = 42,
    run_id: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    artifact_dir = artifact_dir.resolve()

    data_validation_target = artifact_dir / "data_validation.json"
    if data_validation_file.exists() and data_validation_file.resolve() != data_validation_target:
        data_validation = _read_json(data_validation_file, errors)
    else:
        data_validation = _read_json(data_validation_target, errors)
    if data_validation and data_validation.get("valid") is not True:
        errors.append("reports/data_validation.json does not mark the dataset as valid.")

    artifact_paths = {name: artifact_dir / name for name in REQUIRED_ARTIFACTS}
    if data_validation_file.exists() and not artifact_paths["data_validation.json"].exists():
        artifact_paths["data_validation.json"] = data_validation_file

    for name, path in artifact_paths.items():
        if not path.exists():
            errors.append(f"Missing artifact: {name}")

    metrics_json = _read_json(artifact_paths["metrics.json"], errors)
    metrics_csv_rows = _read_csv(artifact_paths["metrics.csv"], errors)
    selected_policy = _read_json(artifact_paths["selected_policy.json"], errors)
    likelihood_model = _read_json(artifact_paths["purchase_likelihood_model.json"], errors)
    golden_set = _read_json_list(artifact_paths["golden_set_recommendations.json"], errors)

    _validate_metrics(metrics_json, metrics_csv_rows, errors)
    _validate_selected_policy(selected_policy, metrics_json, errors)
    _validate_likelihood_model(likelihood_model, errors)
    _validate_golden_set(golden_set, errors)

    if errors:
        raise ArtifactValidationFailure("; ".join(errors))

    manifest = _build_manifest(
        artifact_paths=artifact_paths,
        dataset_file=dataset_file,
        seed=seed,
        run_id=run_id,
    )
    if manifest_file is not None:
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _validate_metrics(
    metrics_json: dict[str, Any],
    metrics_csv_rows: list[dict[str, str]],
    errors: list[str],
) -> None:
    metrics = metrics_json.get("metrics")
    if not isinstance(metrics, list):
        errors.append("metrics.json must contain a metrics list.")
        return
    policies = {str(item.get("policy")) for item in metrics if isinstance(item, dict)}
    if policies != REQUIRED_POLICIES:
        errors.append(f"metrics.json must contain policies {sorted(REQUIRED_POLICIES)}.")

    csv_by_policy = {row.get("policy", ""): row for row in metrics_csv_rows}
    for item in metrics:
        if not isinstance(item, dict):
            errors.append("Each metrics.json item must be an object.")
            continue
        policy = str(item.get("policy", ""))
        csv_row = csv_by_policy.get(policy)
        if csv_row is None:
            errors.append(f"metrics.csv is missing policy {policy}.")
            continue
        for field in METRIC_FIELDS:
            value = item.get(field)
            if not isinstance(value, int | float) or not math.isfinite(float(value)):
                errors.append(f"Metric {policy}.{field} must be finite numeric.")
                continue
            if field == "rounds" and int(value) <= 0:
                errors.append(f"Metric {policy}.rounds must be greater than zero.")
            if field in {"conversion_rate", "exploration_rate"} and not 0 <= float(value) <= 1:
                errors.append(f"Metric {policy}.{field} must be between 0 and 1.")
            if field == "cumulative_regret" and float(value) < 0:
                errors.append(f"Metric {policy}.cumulative_regret must be non-negative.")
            if field in csv_row and _to_number(csv_row[field]) != float(value):
                errors.append(f"metrics.csv does not match metrics.json for {policy}.{field}.")


def _validate_selected_policy(
    selected_policy: dict[str, Any],
    metrics_json: dict[str, Any],
    errors: list[str],
) -> None:
    if selected_policy.get("schema_version") != SELECTED_POLICY_SCHEMA:
        errors.append("selected_policy.json has an incompatible schema_version.")
    if selected_policy.get("artifact_status") != ARTIFACT_STATUS_ACTIVE:
        errors.append("selected_policy.json must be active.")
    policy = selected_policy.get("policy")
    metrics = metrics_json.get("metrics", [])
    by_policy = {item.get("policy"): item for item in metrics if isinstance(item, dict)}
    if policy not in by_policy:
        errors.append("selected_policy.json policy must exist in metrics.json.")
        return
    selected_metrics = selected_policy.get("metrics")
    if not isinstance(selected_metrics, dict):
        errors.append("selected_policy.json must include metrics.")
        return
    for field in METRIC_FIELDS:
        if _to_number(selected_metrics.get(field)) != _to_number(by_policy[policy].get(field)):
            errors.append(f"selected_policy.json metrics do not match metrics.json for {field}.")
    if not selected_policy.get("version"):
        errors.append("selected_policy.json must include version.")
    if not selected_policy.get("selection_rule"):
        errors.append("selected_policy.json must include selection_rule.")


def _validate_likelihood_model(model: dict[str, Any], errors: list[str]) -> None:
    if model.get("schema_version") != LIKELIHOOD_MODEL_SCHEMA:
        errors.append("purchase_likelihood_model.json has an incompatible schema_version.")
    if model.get("artifact_status") != ARTIFACT_STATUS_ACTIVE:
        errors.append("purchase_likelihood_model.json must be active.")
    if not model.get("version"):
        errors.append("purchase_likelihood_model.json must include version.")
    if int(model.get("global_count", 0)) <= 0:
        errors.append("purchase_likelihood_model.json global_count must be greater than zero.")
    global_rate = _to_number(model.get("global_conversion_rate"))
    if global_rate is None or not 0 <= global_rate <= 1:
        errors.append("purchase_likelihood_model.json global_conversion_rate must be between 0 and 1.")
    action_rates = model.get("action_rates")
    if not isinstance(action_rates, dict) or set(action_rates) != set(ACTIONS):
        errors.append("purchase_likelihood_model.json must include all expected actions.")
    elif any(not 0 <= float(value.get("rate", -1)) <= 1 for value in action_rates.values()):
        errors.append("purchase_likelihood_model.json action rates must be between 0 and 1.")
    if int(model.get("min_samples", 0)) <= 0:
        errors.append("purchase_likelihood_model.json min_samples must be positive.")
    if _to_number(model.get("smoothing_alpha")) is None or float(model["smoothing_alpha"]) <= 0:
        errors.append("purchase_likelihood_model.json smoothing_alpha must be positive.")
    if not isinstance(model.get("context_columns"), list) or not model["context_columns"]:
        errors.append("purchase_likelihood_model.json must include context_columns.")


def _validate_golden_set(golden_set: list[Any], errors: list[str]) -> None:
    if len(golden_set) != 5:
        errors.append("golden_set_recommendations.json must contain exactly five cases.")
    sensitive = {"history", "zip_code", "customer_id", "email", "income", "wealth"}
    for index, item in enumerate(golden_set, start=1):
        if not isinstance(item, dict):
            errors.append(f"Golden Set case {index} must be an object.")
            continue
        eligible = item.get("eligible_actions")
        recommended = item.get("recommended_action")
        if not isinstance(eligible, list) or not eligible:
            errors.append(f"Golden Set case {index} must include eligible_actions.")
        elif recommended not in eligible:
            errors.append(f"Golden Set case {index} recommendation must be eligible.")
        if not item.get("reason_codes"):
            errors.append(f"Golden Set case {index} must include reason_codes.")
        context = item.get("context", {})
        if isinstance(context, dict) and sensitive.intersection(context):
            errors.append(f"Golden Set case {index} contains sensitive context fields.")


def _build_manifest(
    *,
    artifact_paths: dict[str, Path],
    dataset_file: Path,
    seed: int,
    run_id: str | None,
) -> dict[str, Any]:
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    git_commit = _git_commit()
    effective_run_id = run_id or f"train-{generated_at.replace('-', '').replace(':', '')}-{git_commit[:7]}"
    artifacts = {
        name: {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        for name, path in artifact_paths.items()
    }
    return {
        "run_id": effective_run_id,
        "git_commit": git_commit,
        "dataset_sha256": sha256_file(dataset_file) if dataset_file.exists() else "",
        "python_version": platform.python_version(),
        "seed": seed,
        "generated_at": generated_at,
        "artifacts": artifacts,
    }


def _read_json(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append(f"{path.name} must be valid JSON.")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.name} must be a JSON object.")
        return {}
    return value


def _read_json_list(path: Path, errors: list[str]) -> list[Any]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append(f"{path.name} must be valid JSON.")
        return []
    if not isinstance(value, list):
        errors.append(f"{path.name} must be a JSON array.")
        return []
    return value


def _read_csv(path: Path, errors: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _to_number(value: Any) -> float | None:
    if isinstance(value, int | float) and math.isfinite(float(value)):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _git_commit() -> str:
    env_commit = os.getenv("GITHUB_SHA")
    if env_commit:
        return env_commit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ECloe training artifacts.")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--data-validation-file", type=Path, default=DEFAULT_DATA_VALIDATION_FILE)
    parser.add_argument("--dataset-file", type=Path, default=DEFAULT_DATASET_FILE)
    parser.add_argument("--manifest-file", type=Path, default=DEFAULT_MANIFEST_FILE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    manifest = validate_artifacts(
        artifact_dir=args.artifact_dir,
        data_validation_file=args.data_validation_file,
        dataset_file=args.dataset_file,
        manifest_file=args.manifest_file,
        seed=args.seed,
        run_id=args.run_id,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
