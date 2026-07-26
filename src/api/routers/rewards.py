from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.api.dependencies import get_decision_repository, get_request_context
from src.api.errors import API_ERROR_RESPONSES, invalid_request
from src.api.schemas.rewards import RewardRequest, RewardResponse
from src.api.security import Principal, require_scopes, subject_key_for
from src.core.config import Settings, load_settings
from src.storage.decision_repository import DecisionRepository, RewardRecord

router = APIRouter(prefix="/v1/rewards", tags=["rewards"])


@router.post("", response_model=RewardResponse, responses=API_ERROR_RESPONSES)
def ingest_reward(
    payload: RewardRequest,
    principal: Annotated[Principal, Depends(require_scopes("reward:write"))],
    repository: Annotated[DecisionRepository, Depends(get_decision_repository)],
    settings: Annotated[Settings, Depends(load_settings)],
    request_context: Annotated[Request | None, Depends(get_request_context)] = None,
) -> dict[str, object]:
    try:
        subject_key = subject_key_for(principal, settings)
        existing_reward = repository.get_reward_by_event_id(
            subject_key=subject_key,
            event_id=payload.event_id,
        )
        if existing_reward is not None:
            if hasattr(request_context, "state"):
                request_context.state.decision_id = existing_reward.decision_id
            return existing_reward.response

        decision = repository.get_decision(
            subject_key=subject_key,
            decision_id=payload.decision_id,
        )
        if decision is None:
            raise ValueError("decision_id does not exist for this subject")

        occurred_at = payload.occurred_at.astimezone(UTC)
        decision_created_at = datetime.fromisoformat(decision.created_at).astimezone(UTC)
        if occurred_at < decision_created_at:
            raise ValueError("occurred_at cannot be earlier than the decision timestamp")

        response = {
            "decision_id": payload.decision_id,
            "event_id": payload.event_id,
            "event_type": payload.event_type.value,
            "reward": payload.reward,
            "occurred_at": occurred_at.isoformat(),
            "accepted": True,
        }
        saved = repository.save_reward(
            RewardRecord(
                event_id=payload.event_id,
                decision_id=payload.decision_id,
                subject_key=subject_key,
                event_type=payload.event_type.value,
                reward=payload.reward,
                occurred_at=occurred_at.isoformat(),
                created_at=datetime.now(UTC).isoformat(),
                response=response,
                ttl=settings.decision_event_ttl_seconds,
            )
        )
        if hasattr(request_context, "state"):
            request_context.state.decision_id = saved.decision_id
    except ValueError as error:
        raise invalid_request(error) from error
    return saved.response
