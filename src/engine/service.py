from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import Path

from src.engine.artifacts import SELECTED_POLICY_SCHEMA, ArtifactMetadata, LoadedArtifact, load_json_artifact
from src.engine.likelihood import DEFAULT_OUTPUT_DIR, PurchaseLikelihoodService
from src.engine.schemas import DecisionResponse, EngineRequest, LikelihoodEstimate
from src.engine.strategies import DecisionStrategy, LikelihoodRankerStrategy


DEFAULT_SELECTED_POLICY_FILE = DEFAULT_OUTPUT_DIR / "selected_policy.json"


class DecisionService:
    def __init__(
        self,
        likelihood_service: PurchaseLikelihoodService,
        selected_policy: dict[str, object],
        selected_policy_metadata: ArtifactMetadata,
        strategy: DecisionStrategy | None = None,
        selected_policy_file: Path = DEFAULT_SELECTED_POLICY_FILE,
    ) -> None:
        self.likelihood_service = likelihood_service
        self.selected_policy = selected_policy
        self.selected_policy_metadata = selected_policy_metadata
        self.strategy = strategy or LikelihoodRankerStrategy(likelihood_service.artifact_metadata)
        self.selected_policy_file = selected_policy_file

    @classmethod
    def from_files(
        cls,
        likelihood_model_file: Path | None = None,
        selected_policy_file: Path = DEFAULT_SELECTED_POLICY_FILE,
    ) -> "DecisionService":
        service = (
            PurchaseLikelihoodService.from_file(likelihood_model_file)
            if likelihood_model_file is not None
            else PurchaseLikelihoodService.from_file()
        )
        selected_policy_artifact = load_selected_policy_artifact(selected_policy_file)
        return cls(
            likelihood_service=service,
            selected_policy=selected_policy_artifact.payload,
            selected_policy_metadata=selected_policy_artifact.metadata,
            selected_policy_file=selected_policy_file,
        )

    def current_policy(self) -> dict[str, object]:
        artifact = self.strategy.artifact_metadata
        return {
            "policy": self.strategy.name,
            "version": self.strategy.version,
            "status": "active",
            "artifact_schema": artifact.schema_version,
            "artifact_version": artifact.version,
            "artifact_checksum": artifact.checksum,
            "artifact_status": artifact.status,
            "artifact_path": artifact.path,
            "promoted_offline_policy": self.selected_policy,
            "promoted_offline_policy_artifact": {
                "schema": self.selected_policy_metadata.schema_version,
                "version": self.selected_policy_metadata.version,
                "checksum": self.selected_policy_metadata.checksum,
                "status": self.selected_policy_metadata.status,
                "path": self.selected_policy_metadata.path,
            },
        }

    def decide(self, request: EngineRequest) -> DecisionResponse:
        likelihood = self.likelihood_service.estimate(request)
        selected = self.strategy.select(request, likelihood)
        artifact = self.strategy.artifact_metadata
        decision_id = self._decision_id(request.request_id, selected)
        return DecisionResponse(
            request_id=request.request_id,
            decision_id=decision_id,
            offer_id=selected.offer_id,
            purchase_likelihood=selected.purchase_likelihood,
            policy=self.strategy.name,
            policy_version=self.strategy.version,
            artifact_schema=artifact.schema_version,
            artifact_version=artifact.version,
            artifact_checksum=artifact.checksum,
            artifact_status=artifact.status,
            reason_codes=[
                "highest_validated_purchase_likelihood",
                *selected.reason_codes,
            ],
            warnings=likelihood.warnings,
        )

    @staticmethod
    def _decision_id(request_id: str, selected: LikelihoodEstimate) -> str:
        payload = f"{request_id}:{selected.offer_id}:{selected.purchase_likelihood}"
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return f"dec_{digest}"


def load_selected_policy_artifact(path: Path) -> LoadedArtifact:
    return load_json_artifact(
        path,
        expected_schema=SELECTED_POLICY_SCHEMA,
        required_fields={"policy", "version", "selection_rule", "metrics"},
    )


def to_dict(value: object) -> dict[str, object]:
    return asdict(value)
