from __future__ import annotations

# ruff: noqa: E402, I001

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.api.main import create_app


REQUIRED_OPERATIONS = {
    ("/v1/policies/current", "get"),
    ("/v1/likelihood-estimates", "post"),
    ("/v1/purchase-likelihood", "post"),
    ("/v1/decisions", "post"),
    ("/v1/rewards", "post"),
}
REQUIRED_ERROR_CODES = {"401", "403", "422", "500"}


def main() -> None:
    contract = create_app().openapi()
    paths = contract.get("paths", {})
    missing = []
    incompatible = []

    for path, method in sorted(REQUIRED_OPERATIONS):
        operation = paths.get(path, {}).get(method)
        if operation is None:
            missing.append(f"{method.upper()} {path}")
            continue
        if "requestBody" not in operation and method == "post":
            incompatible.append(f"{method.upper()} {path} is missing requestBody")
        responses = set(operation.get("responses", {}))
        missing_errors = sorted(REQUIRED_ERROR_CODES - responses)
        if missing_errors:
            incompatible.append(
                f"{method.upper()} {path} is missing error responses: {missing_errors}"
            )

    if missing or incompatible:
        detail = "\n".join([*missing, *incompatible])
        raise SystemExit(f"OpenAPI contract is incompatible:\n{detail}")


if __name__ == "__main__":
    main()
