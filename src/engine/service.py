from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from src.engine.likelihood import DEFAULT_OUTPUT_DIR, PurchaseLikelihoodService
from src.engine.schemas import DecisionResponse, EngineRequest, LikelihoodEstimate


DEFAULT_SELECTED_POLICY_FILE = DEFAULT_OUTPUT_DIR / "selected_policy.json"


class DecisionService:
    def __init__(
        self,
        likelihood_service: PurchaseLikelihoodService,
        selected_policy_file: Path = DEFAULT_SELECTED_POLICY_FILE,
    ) -> None:
        self.likelihood_service = likelihood_service
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
        return cls(likelihood_service=service, selected_policy_file=selected_policy_file)

    def current_policy(self) -> dict[str, object]:
        if not self.selected_policy_file.exists():
            return {
                "policy": "likelihood_ranker",
                "version": "likelihood-v1",
                "source": "fallback",
            }
        return json.loads(self.selected_policy_file.read_text(encoding="utf-8"))

    def decide(self, request: EngineRequest) -> DecisionResponse:
        likelihood = self.likelihood_service.estimate(request)
        selected = max(
            likelihood.estimates,
            key=lambda estimate: (
                estimate.purchase_likelihood,
                -request.eligible_offers.index(estimate.offer_id),
            ),
        )
        policy = self.current_policy()
        decision_id = self._decision_id(request.request_id, selected)
        return DecisionResponse(
            request_id=request.request_id,
            decision_id=decision_id,
            offer_id=selected.offer_id,
            purchase_likelihood=selected.purchase_likelihood,
            policy=str(policy.get("policy", "likelihood_ranker")),
            policy_version=str(policy.get("version", "likelihood-v1")),
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


def to_dict(value: object) -> dict[str, object]:
    return asdict(value)
