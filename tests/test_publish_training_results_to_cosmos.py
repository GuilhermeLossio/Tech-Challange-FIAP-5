from __future__ import annotations

import json

from scripts.publish_training_results_to_cosmos import build_training_result_documents


def test_build_training_result_documents_uses_policy_name_partition_key(tmp_path) -> None:
    artifact_dir = tmp_path / "policy_training"
    artifact_dir.mkdir()
    (artifact_dir / "policy_versions.json").write_text(
        json.dumps(
            [
                {
                    "policy_name": "baseline",
                    "version": "offline-v1",
                    "status": "selected",
                    "metrics": {"rounds": 10},
                }
            ]
        ),
        encoding="utf-8",
    )
    (artifact_dir / "selected_policy.json").write_text(
        json.dumps({"policy": "baseline", "version": "offline-v1"}),
        encoding="utf-8",
    )
    (artifact_dir / "artifact_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "train-test",
                "git_commit": "abc",
                "dataset_sha256": "def",
                "python_version": "3.14.6",
                "seed": 42,
                "generated_at": "2026-07-27T21:16:36Z",
                "artifacts": {
                    "policy_versions.json": {"sha256": "policy-sha"},
                    "selected_policy.json": {"sha256": "selected-sha"},
                },
            }
        ),
        encoding="utf-8",
    )

    documents = build_training_result_documents(artifact_dir)

    assert len(documents) == 2
    assert documents[0]["id"] == "train-test:baseline:offline-v1"
    assert documents[0]["policy_name"] == "baseline"
    assert documents[0]["record_type"] == "policy_version"
    assert documents[0]["artifact_manifest"]["policy_versions_sha256"] == "policy-sha"
    assert documents[1]["id"] == "train-test:training_run"
    assert documents[1]["policy_name"] == "__training_run__"
