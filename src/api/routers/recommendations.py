from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from src.api.dependencies import (
    get_decision_repository,
    get_recommendation_service,
    to_recommendation_request,
)
from src.api.errors import API_ERROR_RESPONSES, idempotency_conflict, invalid_request
from src.api.schemas.recommendations import (
    FeedbackRequestV2,
    FeedbackResponseV2,
    LikelihoodEstimatesResponseV2,
    RecommendationDecisionResponse,
    RecommendationPolicyResponse,
    RecommendationReloadRequest,
    RecommendationReloadResponse,
    RecommendationRequestV2,
)
from src.api.security import Principal, require_scopes, subject_key_for
from src.core.config import Settings, load_settings
from src.engine.artifact_sources import load_recommendation_runtime
from src.recommendation import RecommendationService, Surface
from src.storage.decision_repository import (
    DecisionRecord,
    DecisionRepository,
    IdempotencyConflict,
    RewardRecord,
    request_hash,
)

router = APIRouter(prefix="/v2", tags=["recommendations-v2"])
logger = logging.getLogger(__name__)


@router.post("/decisions", response_model=RecommendationDecisionResponse, responses=API_ERROR_RESPONSES)
def create_recommendation(
    payload: RecommendationRequestV2,
    principal: Annotated[Principal, Depends(require_scopes("decision:write"))],
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
    repository: Annotated[DecisionRepository, Depends(get_decision_repository)],
    settings: Annotated[Settings, Depends(load_settings)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ] = None,
) -> dict[str, object]:
    try:
        subject_key = subject_key_for(principal, settings)
        payload_hash = request_hash(payload.model_dump(mode="json"))
        if idempotency_key:
            existing = repository.get_by_idempotency_key(
                subject_key=subject_key, idempotency_key=idempotency_key
            )
            if existing is not None:
                if existing.request_hash and existing.request_hash != payload_hash:
                    raise IdempotencyConflict("Idempotency-Key was already used with a different request")
                return existing.response

        request = to_recommendation_request(payload)
        decision = service.decide(request)
        response = asdict(decision)
        response.pop("shadow_rankings", None)
        ranked = response["ranked_candidates"]
        selected = ranked[0]
        saved = repository.save_decision(
            DecisionRecord(
                decision_id=decision.decision_id,
                subject_key=subject_key,
                request_id=decision.request_id,
                selected_offer_id=selected["candidate_id"],
                policy=decision.policy,
                policy_version=decision.policy_version,
                artifact_version=decision.artifact_version,
                artifact_checksum=decision.artifact_checksum,
                reason_codes=list(selected["reason_codes"]),
                created_at=decision.created_at,
                minimized_context=request.context,
                response=response,
                idempotency_key=idempotency_key,
                request_hash=payload_hash,
                ttl=settings.decision_event_ttl_seconds,
                surface=decision.surface.value,
                decision_point=decision.decision_point,
                selected_candidate_id=selected["candidate_id"],
                candidate_type=selected["candidate_type"].value,
                eligible_candidate_ids=[candidate.candidate_id for candidate in request.candidates],
                ranked_candidates=ranked,
                selection_probability=float(selected["selection_probability"]),
                behavior_policy=decision.policy,
                behavior_policy_version=decision.policy_version,
                behavior_propensity=float(selected["selection_probability"]),
                propensity_source=(
                    "deterministic"
                    if decision.policy == "deterministic_baseline"
                    else "runtime_policy"
                ),
                candidate_propensities={
                    item["candidate_id"]: float(item["selection_probability"])
                    for item in ranked
                },
            )
        )
        return saved.response
    except IdempotencyConflict as error:
        raise idempotency_conflict(error) from error
    except ValueError as error:
        raise invalid_request(error) from error


@router.post(
    "/likelihood-estimates",
    response_model=LikelihoodEstimatesResponseV2,
    responses=API_ERROR_RESPONSES,
)
def likelihood_estimates(
    payload: RecommendationRequestV2,
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
    _: Annotated[Principal, Depends(require_scopes("decision:read"))],
) -> dict[str, object]:
    try:
        request = to_recommendation_request(payload)
        estimates = service.estimates(request)
        return {
            "request_id": request.request_id,
            "surface": request.surface.value,
            "estimates": [asdict(estimate) for estimate in estimates],
            "warnings": [],
        }
    except ValueError as error:
        raise invalid_request(error) from error


@router.post("/feedback", response_model=FeedbackResponseV2, responses=API_ERROR_RESPONSES)
def record_feedback(
    payload: FeedbackRequestV2,
    principal: Annotated[Principal, Depends(require_scopes("reward:write"))],
    repository: Annotated[DecisionRepository, Depends(get_decision_repository)],
    settings: Annotated[Settings, Depends(load_settings)],
) -> dict[str, object]:
    try:
        subject_key = subject_key_for(principal, settings)
        existing = repository.get_reward_by_event_id(subject_key=subject_key, event_id=payload.event_id)
        if existing is not None:
            if (
                existing.decision_id != payload.decision_id
                or existing.candidate_id != payload.candidate_id
                or existing.position != payload.position
                or existing.event_type != payload.event_type
            ):
                raise IdempotencyConflict("event_id was already used with different feedback")
            return existing.response
        decision = repository.get_decision(subject_key=subject_key, decision_id=payload.decision_id)
        if decision is None:
            raise ValueError("decision_id does not exist for this subject")
        ranked = decision.ranked_candidates or decision.response.get("ranked_candidates", [])
        match = next(
            (
                candidate
                for candidate in ranked
                if candidate.get("candidate_id") == payload.candidate_id
                and int(candidate.get("rank", 0)) == payload.position
            ),
            None,
        )
        if match is None:
            raise ValueError("candidate_id and position were not presented by this decision")
        occurred_at = payload.occurred_at.astimezone(UTC)
        if occurred_at < datetime.fromisoformat(decision.created_at).astimezone(UTC):
            raise ValueError("occurred_at cannot be earlier than the decision timestamp")
        terminal, reward = _feedback_outcome(decision.surface, payload.event_type)
        response = {
            "decision_id": payload.decision_id,
            "event_id": payload.event_id,
            "candidate_id": payload.candidate_id,
            "position": payload.position,
            "event_type": payload.event_type,
            "occurred_at": occurred_at.isoformat(),
            "terminal": terminal,
            "reward": reward,
            "recorded": True,
        }
        saved = repository.save_reward(
            RewardRecord(
                event_id=payload.event_id,
                decision_id=payload.decision_id,
                subject_key=subject_key,
                event_type=payload.event_type,
                reward=reward or 0.0,
                occurred_at=occurred_at.isoformat(),
                created_at=datetime.now(UTC).isoformat(),
                response=response,
                request_hash=request_hash(payload.model_dump(mode="json")),
                ttl=settings.decision_event_ttl_seconds,
                surface=decision.surface,
                candidate_id=payload.candidate_id,
                position=payload.position,
                terminal=terminal,
            )
        )
        return saved.response
    except IdempotencyConflict as error:
        raise idempotency_conflict(error) from error
    except (TypeError, ValueError) as error:
        raise invalid_request(error) from error


@router.get(
    "/policies/current",
    response_model=RecommendationPolicyResponse,
    responses=API_ERROR_RESPONSES,
)
def current_recommendation_policy(
    surface: Surface,
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
    _: Annotated[Principal, Depends(require_scopes("policy:read"))],
) -> dict[str, object]:
    return service.current_policy(surface)


@router.post(
    "/policies/reload",
    response_model=RecommendationReloadResponse,
    responses=API_ERROR_RESPONSES,
)
def reload_recommendation_policy(
    payload: RecommendationReloadRequest,
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
    settings: Annotated[Settings, Depends(load_settings)],
    _: Annotated[Principal, Depends(require_scopes("policy:reload"))],
) -> dict[str, object]:
    try:
        surfaces = (
            (Surface.market, Surface.pay)
            if payload.surface == "all"
            else (payload.surface,)
        )
        runtimes = {
            surface: load_recommendation_runtime(settings, surface)
            for surface in surfaces
        }
        result = service.reload(runtimes)
        logger.info("Recommendation policy reload completed surfaces=%s", sorted(result))
        return {"reloaded": result}
    except (TypeError, ValueError, FileNotFoundError, RuntimeError) as error:
        logger.warning("Recommendation policy reload rejected reason=%s", type(error).__name__)
        raise invalid_request(error) from error


def _feedback_outcome(surface: str, event_type: str) -> tuple[bool, float | None]:
    if surface == Surface.market.value:
        if event_type == "purchase":
            return True, 1.0
        if event_type == "expired":
            return True, 0.0
        if event_type in {"impression", "click", "add_to_cart"}:
            return False, None
        raise ValueError(f"event_type={event_type} is not valid for surface=market")
    if event_type == "acceptance":
        return True, 1.0
    if event_type in {"dismissal", "rejection", "expired"}:
        return True, 0.0
    if event_type in {"impression", "click", "open"}:
        return False, None
    raise ValueError(f"event_type={event_type} is not valid for surface=pay")
