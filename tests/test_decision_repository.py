from __future__ import annotations

from src.storage.decision_repository import (
    DecisionRecord,
    FileDecisionRepository,
    RewardRecord,
    _record_from_dict,
    _record_to_dict,
    _reward_from_dict,
    _reward_to_dict,
)


def test_file_decision_repository_reloads_idempotency_records(tmp_path) -> None:
    path = tmp_path / "decision_events.jsonl"
    repository = FileDecisionRepository(path)
    record = DecisionRecord(
        decision_id="dec_123",
        subject_key="sub_abc",
        request_id="req_1",
        selected_offer_id="cashback_recurring_purchase",
        policy="likelihood_ranker",
        policy_version="likelihood-v1",
        artifact_version="likelihood-v1",
        artifact_checksum="a" * 64,
        reason_codes=["highest_validated_purchase_likelihood"],
        created_at="2026-07-22T12:00:00+00:00",
        minimized_context={"channel": "Web"},
        response={"decision_id": "dec_123"},
        idempotency_key="idem-1",
        request_hash="b" * 64,
        ttl=157680000,
    )

    repository.save_decision(record)
    reward = RewardRecord(
        event_id="evt_123",
        decision_id="dec_123",
        subject_key="sub_abc",
        event_type="conversion",
        reward=1.0,
        occurred_at="2026-07-22T12:01:00+00:00",
        created_at="2026-07-22T12:01:01+00:00",
        response={"event_id": "evt_123"},
        ttl=157680000,
    )
    repository.save_reward(reward)
    reloaded = FileDecisionRepository(path)

    assert reloaded.event_count == 1
    assert len(reloaded.reward_records) == 1
    assert (
        reloaded.get_by_idempotency_key(subject_key="sub_abc", idempotency_key="idem-1")
        == record
    )
    assert reloaded.get_reward_by_event_id(subject_key="sub_abc", event_id="evt_123") == reward


def test_cosmos_document_payload_uses_existing_customer_id_partition_alias() -> None:
    decision = DecisionRecord(
        decision_id="dec_1",
        subject_key="sub_hash",
        request_id="req_1",
        selected_offer_id="offer",
        policy="likelihood_ranker",
        policy_version="likelihood-v1",
        artifact_version="likelihood-v1",
        artifact_checksum="abc",
        reason_codes=["test"],
        created_at="2026-07-27T20:00:00+00:00",
        minimized_context={},
        response={},
    )
    reward = RewardRecord(
        event_id="evt_1",
        decision_id="dec_1",
        subject_key="sub_hash",
        event_type="conversion",
        reward=1.0,
        occurred_at="2026-07-27T20:01:00+00:00",
        created_at="2026-07-27T20:01:01+00:00",
        response={},
    )

    decision_payload = _record_to_dict(decision)
    reward_payload = _reward_to_dict(reward)

    assert decision_payload["customer_id"] == "sub_hash"
    assert reward_payload["customer_id"] == "sub_hash"
    assert _record_from_dict({"customer_id": "sub_hash", **decision_payload}).subject_key == "sub_hash"
    assert _reward_from_dict({"customer_id": "sub_hash", **reward_payload}).subject_key == "sub_hash"
