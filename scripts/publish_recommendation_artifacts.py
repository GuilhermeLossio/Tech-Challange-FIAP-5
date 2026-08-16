from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.publish_artifacts_to_blob import (
    _artifact_container,
    _content_settings,
    _ensure_container,
)
from src.core.config import load_settings
from src.recommendation.models import Surface


def publish_recommendation_run(
    run_dir: Path,
    *,
    surface: Surface,
    promote: bool = False,
) -> dict[str, object]:
    settings = load_settings()
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("surface") != surface.value:
        raise ValueError("Recommendation artifact surface does not match the command surface.")
    selected = json.loads((run_dir / "selected_policy.json").read_text(encoding="utf-8"))
    if promote and selected.get("artifact_status") != "active":
        raise ValueError("Only an approved active recommendation run can be promoted.")
    container = _artifact_container(settings)
    _ensure_container(container)
    run_id = str(manifest["run_id"])
    uploaded: list[str] = []
    for name in (
        "artifact_manifest.json",
        "recommendation_evidence.json",
        "selected_policy.json",
        "metrics.json",
        "golden_set_recommendations.json",
    ):
        blob = f"runs/{surface.value}/{run_id}/{name}"
        container.upload_blob(
            blob,
            (run_dir / name).read_bytes(),
            overwrite=False,
            content_settings=_content_settings(name),
        )
        uploaded.append(blob)
    promoted_blob = None
    if promote:
        promoted_blob = (
            settings.azure_artifact_promotion_blob_market
            if surface is Surface.market
            else settings.azure_artifact_promotion_blob_pay
        )
        pointer = {
            "surface": surface.value,
            "run_id": run_id,
            "manifest_blob": f"runs/{surface.value}/{run_id}/artifact_manifest.json",
            "promoted_at": datetime.now(UTC).isoformat(),
        }
        container.upload_blob(
            promoted_blob,
            json.dumps(pointer, indent=2).encode("utf-8"),
            overwrite=True,
            content_settings=_content_settings("current.json"),
        )
    return {"surface": surface.value, "run_id": run_id, "uploaded": uploaded, "promoted_blob": promoted_blob}


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a reviewed recommendation artifact run.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--surface", choices=[surface.value for surface in Surface], required=True)
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    print(json.dumps(publish_recommendation_run(args.run_dir, surface=Surface(args.surface), promote=args.promote), indent=2))


if __name__ == "__main__":
    main()
