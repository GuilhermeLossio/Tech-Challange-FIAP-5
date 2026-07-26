from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

from src.core.config import Settings


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    subject_key: str
    request_id: str
    selected_offer_id: str
    policy: str
    policy_version: str
    artifact_version: str
    artifact_checksum: str
    reason_codes: list[str]
    created_at: str
    minimized_context: dict[str, Any]
    response: dict[str, Any]
    idempotency_key: str | None = None
    request_hash: str = ""
    ttl: int | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "decision"

    @property
    def partition_key(self) -> str:
        return self.subject_key


@dataclass(frozen=True)
class RewardRecord:
    event_id: str
    decision_id: str
    subject_key: str
    event_type: str
    reward: float
    occurred_at: str
    created_at: str
    response: dict[str, Any]
    ttl: int | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    record_type: str = "reward"

    @property
    def partition_key(self) -> str:
        return self.subject_key


class DecisionRepository(Protocol):
    def get_decision(
        self,
        *,
        subject_key: str,
        decision_id: str,
    ) -> DecisionRecord | None:
        pass

    def get_by_idempotency_key(
        self,
        *,
        subject_key: str,
        idempotency_key: str,
    ) -> DecisionRecord | None:
        pass

    def save_decision(self, record: DecisionRecord) -> DecisionRecord:
        pass

    def get_reward_by_event_id(
        self,
        *,
        subject_key: str,
        event_id: str,
    ) -> RewardRecord | None:
        pass

    def save_reward(self, record: RewardRecord) -> RewardRecord:
        pass


class InMemoryDecisionRepository:
    def __init__(self) -> None:
        self._records: list[DecisionRecord] = []
        self._reward_records: list[RewardRecord] = []
        self._idempotency: dict[tuple[str, str], DecisionRecord] = {}
        self._decisions: dict[tuple[str, str], DecisionRecord] = {}
        self._reward_idempotency: dict[tuple[str, str], RewardRecord] = {}
        self._lock = Lock()

    @property
    def event_count(self) -> int:
        return len(self._records)

    @property
    def records(self) -> tuple[DecisionRecord, ...]:
        with self._lock:
            return tuple(self._records)

    @property
    def reward_records(self) -> tuple[RewardRecord, ...]:
        with self._lock:
            return tuple(self._reward_records)

    def get_decision(
        self,
        *,
        subject_key: str,
        decision_id: str,
    ) -> DecisionRecord | None:
        with self._lock:
            return self._decisions.get((subject_key, decision_id))

    def get_by_idempotency_key(
        self,
        *,
        subject_key: str,
        idempotency_key: str,
    ) -> DecisionRecord | None:
        with self._lock:
            return self._idempotency.get((subject_key, idempotency_key))

    def save_decision(self, record: DecisionRecord) -> DecisionRecord:
        with self._lock:
            if record.idempotency_key:
                key = (record.subject_key, record.idempotency_key)
                existing = self._idempotency.get(key)
                if existing is not None:
                    return existing
                self._idempotency[key] = record
            self._decisions[(record.subject_key, record.decision_id)] = record
            self._records.append(record)
            return record

    def get_reward_by_event_id(
        self,
        *,
        subject_key: str,
        event_id: str,
    ) -> RewardRecord | None:
        with self._lock:
            return self._reward_idempotency.get((subject_key, event_id))

    def save_reward(self, record: RewardRecord) -> RewardRecord:
        with self._lock:
            key = (record.subject_key, record.event_id)
            existing = self._reward_idempotency.get(key)
            if existing is not None:
                return existing
            self._reward_idempotency[key] = record
            self._reward_records.append(record)
            return record


class FileDecisionRepository(InMemoryDecisionRepository):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__()
        self._load()

    def save_decision(self, record: DecisionRecord) -> DecisionRecord:
        saved = super().save_decision(record)
        if saved is record:
            self._append(_record_to_dict(record))
        return saved

    def save_reward(self, record: RewardRecord) -> RewardRecord:
        saved = super().save_reward(record)
        if saved is record:
            self._append(_reward_to_dict(record))
        return saved

    def _append(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, sort_keys=True) + "\n")

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("record_type") == "reward":
                reward = _reward_from_dict(payload)
                self._reward_records.append(reward)
                self._reward_idempotency[(reward.subject_key, reward.event_id)] = reward
                continue

            record = _record_from_dict(payload)
            self._records.append(record)
            self._decisions[(record.subject_key, record.decision_id)] = record
            if record.idempotency_key:
                self._idempotency[(record.subject_key, record.idempotency_key)] = record


class CosmosDecisionRepository:
    @classmethod
    def from_settings(cls, settings: Settings) -> CosmosDecisionRepository:
        try:
            from azure.cosmos import CosmosClient
        except ModuleNotFoundError as error:
            raise RuntimeError("azure-cosmos is required for DECISION_REPOSITORY_MODE=cosmos.") from error

        credential: Any
        if settings.azure_cosmos_auth_mode == "managed_identity":
            try:
                from azure.identity import DefaultAzureCredential
            except ModuleNotFoundError as error:
                raise RuntimeError(
                    "azure-identity is required for Cosmos DB Managed Identity."
                ) from error
            credential = DefaultAzureCredential()
        elif settings.azure_cosmos_key:
            credential = settings.azure_cosmos_key
        else:
            raise RuntimeError("Cosmos DB credential is not configured.")

        client = CosmosClient(settings.azure_cosmos_endpoint, credential=credential)
        database = client.get_database_client(settings.azure_cosmos_database)
        return cls(
            database.get_container_client(settings.azure_cosmos_container_decisions),
            database.get_container_client(settings.azure_cosmos_container_rewards),
        )

    def __init__(self, decision_container: Any, reward_container: Any) -> None:
        self.container = decision_container
        self.reward_container = reward_container

    def get_decision(
        self,
        *,
        subject_key: str,
        decision_id: str,
    ) -> DecisionRecord | None:
        query = (
            "SELECT * FROM c WHERE c.subject_key = @subject_key "
            "AND c.decision_id = @decision_id OFFSET 0 LIMIT 1"
        )
        items = self.container.query_items(
            query=query,
            parameters=[
                {"name": "@subject_key", "value": subject_key},
                {"name": "@decision_id", "value": decision_id},
            ],
            partition_key=subject_key,
        )
        for item in items:
            return _record_from_dict(item)
        return None

    def get_by_idempotency_key(
        self,
        *,
        subject_key: str,
        idempotency_key: str,
    ) -> DecisionRecord | None:
        query = (
            "SELECT * FROM c WHERE c.subject_key = @subject_key "
            "AND c.idempotency_key = @idempotency_key OFFSET 0 LIMIT 1"
        )
        items = self.container.query_items(
            query=query,
            parameters=[
                {"name": "@subject_key", "value": subject_key},
                {"name": "@idempotency_key", "value": idempotency_key},
            ],
            partition_key=subject_key,
        )
        for item in items:
            return _record_from_dict(item)
        return None

    def save_decision(self, record: DecisionRecord) -> DecisionRecord:
        if record.idempotency_key:
            existing = self.get_by_idempotency_key(
                subject_key=record.subject_key,
                idempotency_key=record.idempotency_key,
            )
            if existing is not None:
                return existing
        self.container.create_item(_record_to_dict(record))
        return record

    def get_reward_by_event_id(
        self,
        *,
        subject_key: str,
        event_id: str,
    ) -> RewardRecord | None:
        query = (
            "SELECT * FROM c WHERE c.subject_key = @subject_key "
            "AND c.event_id = @event_id OFFSET 0 LIMIT 1"
        )
        items = self.reward_container.query_items(
            query=query,
            parameters=[
                {"name": "@subject_key", "value": subject_key},
                {"name": "@event_id", "value": event_id},
            ],
            partition_key=subject_key,
        )
        for item in items:
            return _reward_from_dict(item)
        return None

    def save_reward(self, record: RewardRecord) -> RewardRecord:
        existing = self.get_reward_by_event_id(
            subject_key=record.subject_key,
            event_id=record.event_id,
        )
        if existing is not None:
            return existing
        self.reward_container.create_item(_reward_to_dict(record))
        return record


def create_decision_repository(settings: Settings) -> DecisionRepository:
    if settings.decision_repository_mode == "memory":
        return InMemoryDecisionRepository()
    if settings.decision_repository_mode == "file":
        return FileDecisionRepository(settings.decision_events_file)
    if settings.decision_repository_mode == "cosmos":
        return CosmosDecisionRepository.from_settings(settings)
    raise RuntimeError(f"Unsupported DECISION_REPOSITORY_MODE: {settings.decision_repository_mode}")


def request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_to_dict(record: DecisionRecord) -> dict[str, Any]:
    return {
        "decision_id": record.decision_id,
        "subject_key": record.subject_key,
        "request_id": record.request_id,
        "selected_offer_id": record.selected_offer_id,
        "policy": record.policy,
        "policy_version": record.policy_version,
        "artifact_version": record.artifact_version,
        "artifact_checksum": record.artifact_checksum,
        "reason_codes": record.reason_codes,
        "created_at": record.created_at,
        "minimized_context": record.minimized_context,
        "response": record.response,
        "idempotency_key": record.idempotency_key,
        "request_hash": record.request_hash,
        "ttl": record.ttl,
        "id": record.id,
        "event_type": record.event_type,
    }


def _record_from_dict(payload: dict[str, Any]) -> DecisionRecord:
    allowed = {item.name for item in fields(DecisionRecord)}
    return DecisionRecord(**{key: payload[key] for key in allowed if key in payload})


def _reward_to_dict(record: RewardRecord) -> dict[str, Any]:
    return {
        "event_id": record.event_id,
        "decision_id": record.decision_id,
        "subject_key": record.subject_key,
        "event_type": record.event_type,
        "reward": record.reward,
        "occurred_at": record.occurred_at,
        "created_at": record.created_at,
        "response": record.response,
        "ttl": record.ttl,
        "id": record.id,
        "record_type": record.record_type,
    }


def _reward_from_dict(payload: dict[str, Any]) -> RewardRecord:
    allowed = {item.name for item in fields(RewardRecord)}
    return RewardRecord(**{key: payload[key] for key in allowed if key in payload})
