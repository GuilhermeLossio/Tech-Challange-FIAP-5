from __future__ import annotations

from src.storage.decision_repository import DecisionRecord, FileDecisionRepository


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
    reloaded = FileDecisionRepository(path)

    assert reloaded.event_count == 1
    assert (
        reloaded.get_by_idempotency_key(subject_key="sub_abc", idempotency_key="idem-1")
        == record
    )
