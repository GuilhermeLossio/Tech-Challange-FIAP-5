from __future__ import annotations

from pathlib import Path

from src.core.config import load_settings


def ensure_data_dirs() -> dict[str, Path]:
    settings = load_settings()
    paths = {
        "data": settings.data_dir,
        "raw": settings.raw_data_dir,
        "processed": settings.processed_data_dir,
        "golden_set": settings.data_dir / "golden_set",
        "reports": settings.data_dir.parent / "reports",
    }

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    return paths
