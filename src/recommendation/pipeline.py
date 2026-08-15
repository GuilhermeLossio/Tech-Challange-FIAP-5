from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.recommendation.artifacts import (
    RECOMMENDATION_ARTIFACT_SCHEMA,
    evidence_to_payload,
)
from src.recommendation.feedback import (
    RecommendationFeedbackEvent,
    aggregate_evidence,
    evidence_checksum,
)
from src.recommendation.models import Surface


def build_surface_run(
    events: Iterable[RecommendationFeedbackEvent],
    *,
    output_dir: Path,
    surface: Surface,
    run_id: str,
    version: str | None = None,
) -> dict[str, Any]:
    evidence = aggregate_evidence(events)[surface]
    version = version or f"{surface.value}-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = output_dir / "recommendation_evidence.json"
    selected_path = output_dir / "selected_policy.json"
    metrics_path = output_dir / "metrics.json"
    golden_path = output_dir / "golden_set_recommendations.json"

    evidence_path.write_text(json.dumps(evidence_to_payload(evidence), indent=2), encoding="utf-8")
    metrics_path.write_text(
        json.dumps(
            {
                "surface": surface.value,
                "schema_version": RECOMMENDATION_ARTIFACT_SCHEMA,
                "decisions": evidence.global_stats.count,
                "positives": evidence.global_stats.successes,
                "exposures": evidence.exposure_count,
                "terminal_feedback": evidence.terminal_count,
                "policy": "likelihood_ranker",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    selected_path.write_text(
        json.dumps(
            {
                "schema_version": RECOMMENDATION_ARTIFACT_SCHEMA,
                "artifact_status": "pending_review",
                "surface": surface.value,
                "policy": "likelihood_ranker",
                "version": version,
                "selection_rule": "validated terminal feedback with baseline fallback",
                "metrics": {
                    "decisions": evidence.global_stats.count,
                    "positives": evidence.global_stats.successes,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    golden_path.write_text("[]", encoding="utf-8")
    manifest = _manifest(
        output_dir,
        surface=surface,
        run_id=run_id,
        version=version,
        evidence=evidence,
    )
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def approve_surface_run(
    run_dir: Path,
    *,
    surface: Surface,
    approver: str,
    reason: str,
    pointer_root: Path,
) -> dict[str, Any]:
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("surface") != surface.value:
        raise ValueError("Cannot approve an artifact for another surface.")
    if manifest.get("gates", {}).get("passed") is not True:
        raise ValueError("Recommendation artifact gates have not passed.")
    selected_path = run_dir / "selected_policy.json"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    selected["artifact_status"] = "active"
    selected["approval"] = {
        "approver": approver,
        "approved_at": datetime.now(UTC).isoformat(),
        "reason": reason,
    }
    selected_path.write_text(json.dumps(selected, indent=2), encoding="utf-8")
    manifest["approval"] = selected["approval"]
    manifest["artifacts"]["selected_policy.json"]["sha256"] = _sha256(selected_path)
    manifest["artifacts"]["selected_policy.json"]["size"] = selected_path.stat().st_size
    (run_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    pointer = {
        "surface": surface.value,
        "run_id": manifest["run_id"],
        "manifest_blob": f"runs/{surface.value}/{manifest['run_id']}/artifact_manifest.json",
        "promoted_at": datetime.now(UTC).isoformat(),
    }
    pointer_path = pointer_root / "promoted" / surface.value / "current.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(json.dumps(pointer, indent=2), encoding="utf-8")
    return pointer


def _manifest(
    output_dir: Path,
    *,
    surface: Surface,
    run_id: str,
    version: str,
    evidence: Any,
) -> dict[str, Any]:
    names = (
        "recommendation_evidence.json",
        "selected_policy.json",
        "metrics.json",
        "golden_set_recommendations.json",
    )
    return {
        "schema_version": RECOMMENDATION_ARTIFACT_SCHEMA,
        "surface": surface.value,
        "run_id": run_id,
        "version": version,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_window": {"start": None, "end": datetime.now(UTC).isoformat()},
        "evidence_checksum": evidence_checksum(evidence),
        "gates": {
            "passed": evidence.global_stats.count >= 1_000
            and evidence.global_stats.successes >= 100,
            "minimum_decisions": 1_000,
            "minimum_positives": 100,
        },
        "artifacts": {
            name: {"sha256": _sha256(output_dir / name), "size": (output_dir / name).stat().st_size}
            for name in names
        },
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
