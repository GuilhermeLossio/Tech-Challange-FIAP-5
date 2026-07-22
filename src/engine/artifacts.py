from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


LIKELIHOOD_MODEL_SCHEMA = "purchase_likelihood_model.v1"
SELECTED_POLICY_SCHEMA = "selected_policy.v1"
ARTIFACT_STATUS_ACTIVE = "active"


class ArtifactValidationError(ValueError):
    """Raised when an artifact is present but does not match the serving contract."""


@dataclass(frozen=True)
class ArtifactMetadata:
    schema_version: str
    version: str
    checksum: str
    status: str
    path: str


@dataclass(frozen=True)
class LoadedArtifact:
    payload: dict[str, Any]
    metadata: ArtifactMetadata


def load_json_artifact(
    path: Path,
    *,
    expected_schema: str,
    required_fields: set[str],
    version_field: str = "version",
) -> LoadedArtifact:
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")

    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ArtifactValidationError(f"Artifact is not valid JSON: {path}") from error

    if not isinstance(payload, dict):
        raise ArtifactValidationError(f"Artifact must be a JSON object: {path}")

    missing = sorted(required_fields - set(payload))
    if missing:
        raise ArtifactValidationError(f"Artifact {path} is missing required fields: {missing}")

    schema_version = str(payload.get("schema_version", expected_schema))
    if schema_version != expected_schema:
        raise ArtifactValidationError(
            f"Artifact {path} has schema {schema_version!r}; expected {expected_schema!r}"
        )
    payload["schema_version"] = schema_version

    version = payload.get(version_field)
    if not isinstance(version, str) or not version:
        raise ArtifactValidationError(f"Artifact {path} has an invalid {version_field!r}")

    status = str(payload.get("artifact_status", ARTIFACT_STATUS_ACTIVE))
    if status != ARTIFACT_STATUS_ACTIVE:
        raise ArtifactValidationError(
            f"Artifact {path} has status {status!r}; expected {ARTIFACT_STATUS_ACTIVE!r}"
        )
    payload["artifact_status"] = status

    return LoadedArtifact(
        payload=payload,
        metadata=ArtifactMetadata(
            schema_version=schema_version,
            version=version,
            checksum=checksum,
            status=status,
            path=str(path),
        ),
    )
