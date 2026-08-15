from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from src.demo.ecloe_pay.repositories.memory import MemoryPayRepository
from src.storage.decision_repository import (
    DecisionRecord,
    FileDecisionRepository,
    IdempotencyConflict,
    InMemoryDecisionRepository,
    RewardRecord,
    _record_from_dict,
    _record_to_dict,
    _reward_from_dict,
    _reward_to_dict,
)


def _decision(*, request_hash: str = "a" * 64, key: str = "idem-concurrent") -> DecisionRecord:
    return DecisionRecord(
        decision_id="dec_concurrent",
        subject_key="sub_concurrent",
        request_id="req_concurrent",
        selected_offer_id="offer",
        policy="deterministic_baseline",
        policy_version="v1",
        artifact_version="v1",
        artifact_checksum="b" * 64,
        reason_codes=["test"],
        created_at="2026-08-15T12:00:00+00:00",
        minimized_context={},
        response={"decision_id": "dec_concurrent"},
        idempotency_key=key,
        request_hash=request_hash,
    )


def test_decision_idempotency_is_atomic_under_concurrency() -> None:
    repository = InMemoryDecisionRepository()
    with ThreadPoolExecutor(max_workers=12) as executor:
        saved = list(executor.map(lambda _: repository.save_decision(_decision()), range(48)))

    assert repository.event_count == 1
    assert {id(record) for record in saved} == {id(saved[0])}


def test_decision_idempotency_conflict_is_rejected() -> None:
    repository = InMemoryDecisionRepository()
    repository.save_decision(_decision(request_hash="a" * 64))

    with pytest.raises(IdempotencyConflict):
        repository.save_decision(_decision(request_hash="c" * 64))


def test_reward_idempotency_is_atomic_under_concurrency() -> None:
    repository = InMemoryDecisionRepository()
    reward = RewardRecord(
        event_id="event-concurrent",
        decision_id="dec_concurrent",
        subject_key="sub_concurrent",
        event_type="conversion",
        reward=1.0,
        occurred_at="2026-08-15T12:01:00+00:00",
        created_at="2026-08-15T12:01:01+00:00",
        response={"event_id": "event-concurrent"},
        request_hash="d" * 64,
    )
    with ThreadPoolExecutor(max_workers=12) as executor:
        saved = list(executor.map(lambda _: repository.save_reward(reward), range(48)))

    assert len(repository.reward_records) == 1
    assert {id(record) for record in saved} == {id(saved[0])}


def test_wallet_payment_idempotency_is_atomic_under_concurrency() -> None:
    settings = SimpleNamespace(
        ecloe_pay_demo_user_email="demo@example.com",
        ecloe_pay_demo_user_password="a-secure-demo-password",
        ecloe_pay_initial_balance_cents=50_000,
    )
    repository = MemoryPayRepository(settings)
    user_id = next(iter(repository.users))

    def pay(_: int):
        return repository.pay_market_order(
            user_id=user_id,
            market_order_id="order-concurrent",
            amount_cents=1_000,
            currency="BRL",
            idempotency_key="payment-concurrent",
        )

    with ThreadPoolExecutor(max_workers=12) as executor:
        payments = list(executor.map(pay, range(48)))

    assert len(repository.wallet_payments) == 1
    assert {payment.payment_id for payment in payments} == {payments[0].payment_id}
    assert repository.accounts[user_id].available_balance_cents == 49_000


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
