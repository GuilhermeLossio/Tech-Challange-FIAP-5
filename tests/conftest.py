from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = PROJECT_ROOT / ".ecloe_test_tmp"


def _grant_windows_access(path: Path) -> None:
    if os.name != "nt":
        return

    principal = os.environ.get("USERNAME")
    if not principal:
        return

    subprocess.run(
        [
            "icacls",
            str(path),
            "/grant",
            f"{principal}:(OI)(CI)F",
            "/T",
            "/C",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    _grant_windows_access(TEST_TMP_ROOT)

    safe_name = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_"
        for char in request.node.name
    )[:80]
    path = TEST_TMP_ROOT / f"{safe_name}_{uuid4().hex}"
    path.mkdir()
    _grant_windows_access(path)

    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
