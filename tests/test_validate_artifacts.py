from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.run import run_evaluation
from src.evaluation.validate_artifacts import ArtifactValidationFailure, validate_artifacts
from tests.test_engine_likelihood import processed_dataframe


def write_training_outputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    input_file = tmp_path / "processed.csv"
    output_dir = tmp_path / "policy_training"
    data_validation_file = tmp_path / "data_validation.json"
    processed_dataframe().to_csv(input_file, index=False)
    run_evaluation(input_file=input_file, output_dir=output_dir, seed=42)
    data_validation_file.write_text(
        json.dumps({"valid": True, "rows": 18}),
        encoding="utf-8",
    )
    return input_file, output_dir, data_validation_file


def test_validate_artifacts_writes_manifest(tmp_path) -> None:
    input_file, output_dir, data_validation_file = write_training_outputs(tmp_path)

    manifest = validate_artifacts(
        artifact_dir=output_dir,
        data_validation_file=data_validation_file,
        dataset_file=input_file,
        manifest_file=output_dir / "artifact_manifest.json",
        run_id="train-test",
    )

    assert manifest["run_id"] == "train-test"
    assert manifest["dataset_sha256"]
    assert manifest["artifacts"]["metrics.json"]["sha256"]
    assert (output_dir / "artifact_manifest.json").exists()


def test_validate_artifacts_rejects_inactive_selected_policy(tmp_path) -> None:
    input_file, output_dir, data_validation_file = write_training_outputs(tmp_path)
    selected_file = output_dir / "selected_policy.json"
    selected = json.loads(selected_file.read_text(encoding="utf-8"))
    selected["artifact_status"] = "inactive"
    selected_file.write_text(json.dumps(selected), encoding="utf-8")

    with pytest.raises(ArtifactValidationFailure, match=r"selected_policy\.json must be active"):
        validate_artifacts(
            artifact_dir=output_dir,
            data_validation_file=data_validation_file,
            dataset_file=input_file,
            manifest_file=None,
        )


def test_validate_artifacts_rejects_metrics_csv_mismatch(tmp_path) -> None:
    input_file, output_dir, data_validation_file = write_training_outputs(tmp_path)
    metrics_csv = output_dir / "metrics.csv"
    lines = metrics_csv.read_text(encoding="utf-8").splitlines()
    columns = lines[0].split(",")
    first = lines[1].split(",")
    first[columns.index("conversion_rate")] = "0.999999"
    lines[1] = ",".join(first)
    metrics_csv.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(ArtifactValidationFailure, match=r"metrics\.csv does not match"):
        validate_artifacts(
            artifact_dir=output_dir,
            data_validation_file=data_validation_file,
            dataset_file=input_file,
            manifest_file=None,
        )
