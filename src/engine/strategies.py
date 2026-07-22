from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.engine.artifacts import ArtifactMetadata
from src.engine.schemas import EngineRequest, LikelihoodEstimate, LikelihoodResponse


class DecisionStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def artifact_metadata(self) -> ArtifactMetadata:
        raise NotImplementedError

    @abstractmethod
    def select(self, request: EngineRequest, likelihood: LikelihoodResponse) -> LikelihoodEstimate:
        raise NotImplementedError


@dataclass(frozen=True)
class LikelihoodRankerStrategy(DecisionStrategy):
    _artifact_metadata: ArtifactMetadata

    @property
    def name(self) -> str:
        return "likelihood_ranker"

    @property
    def version(self) -> str:
        return self.artifact_metadata.version

    @property
    def artifact_metadata(self) -> ArtifactMetadata:
        return self._artifact_metadata

    def select(self, request: EngineRequest, likelihood: LikelihoodResponse) -> LikelihoodEstimate:
        return max(
            likelihood.estimates,
            key=lambda estimate: (
                estimate.purchase_likelihood,
                -request.eligible_offers.index(estimate.offer_id),
            ),
        )
