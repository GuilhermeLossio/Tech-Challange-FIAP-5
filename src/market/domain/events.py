from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketplaceEvent:
    event_id: str
    aggregate_id: str
    event_type: str
    payload: dict[str, object]
    is_demo: bool = True


@dataclass(frozen=True)
class OutboxEvent:
    outbox_event_id: str
    aggregate_id: str
    event_type: str
    payload: dict[str, object]
    status: str
    is_demo: bool = True
