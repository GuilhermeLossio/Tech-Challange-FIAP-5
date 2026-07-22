from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.api.schemas.base import StrictApiModel


class ArtifactResponse(StrictApiModel):
    artifact_schema: str = Field(alias="schema")
    version: str
    checksum: str
    status: Literal["active"]


class PromotedPolicyResponse(StrictApiModel):
    policy: str
    version: str
    status: Literal["active"]


class PolicyResponse(StrictApiModel):
    policy: Literal["likelihood_ranker", "thompson_sampling"]
    version: str
    status: Literal["active"]
    artifact_schema: str
    artifact_version: str
    artifact_checksum: str
    artifact_status: Literal["active"]
    promoted_offline_policy: PromotedPolicyResponse
    promoted_offline_policy_artifact: ArtifactResponse
