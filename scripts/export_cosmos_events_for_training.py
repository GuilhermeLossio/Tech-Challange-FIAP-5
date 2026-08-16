from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from src.core.config import Settings, load_settings
from src.data.legacy_hillstrom import normalize_legacy_action
from src.engine.offers import resolve_offer_action
from src.recommendation.privacy import assert_safe_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_FILE = ROOT_DIR / "data" / "processed" / "cosmos_training_events.csv"
TRAINING_FIELDNAMES = [
    "row_id",
    "recency",
    "history_segment",
    "newbie",
    "channel",
    "action",
    "reward",
    "decision_id",
    "event_id",
    "occurred_at",
]


def _cosmos_credential(settings: Settings) -> Any:
    if settings.azure_cosmos_auth_mode == "managed_identity":
        try:
            from azure.identity import DefaultAzureCredential
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "azure-identity is required for AZURE_COSMOS_AUTH_MODE=managed_identity."
            ) from error
        return DefaultAzureCredential()

    if settings.azure_cosmos_key:
        return settings.azure_cosmos_key

    raise RuntimeError("Cosmos DB credential is not configured.")


def _read_cosmos_items(settings: Settings) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        from azure.cosmos import CosmosClient
    except ModuleNotFoundError as error:
        raise RuntimeError("azure-cosmos is required to export Cosmos DB events.") from error

    client = CosmosClient(settings.azure_cosmos_endpoint, credential=_cosmos_credential(settings))
    database = client.get_database_client(settings.azure_cosmos_database)
    decisions = database.get_container_client(settings.azure_cosmos_container_decisions)
    rewards = database.get_container_client(settings.azure_cosmos_container_rewards)

    decision_items = list(
        decisions.query_items(
            query="SELECT * FROM c WHERE IS_DEFINED(c.decision_id)",
            enable_cross_partition_query=True,
        )
    )
    reward_items = list(
        rewards.query_items(
            query="SELECT * FROM c WHERE IS_DEFINED(c.event_id) AND IS_DEFINED(c.decision_id)",
            enable_cross_partition_query=True,
        )
    )
    return decision_items, reward_items


def _read_jsonl_events(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisions: list[dict[str, Any]] = []
    rewards: list[dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(path)

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("record_type") == "reward":
            rewards.append(payload)
        elif payload.get("decision_id"):
            decisions.append(payload)
    return decisions, rewards


def _reward_by_decision(
    rewards: list[dict[str, Any]],
    positive_event_type: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for reward in rewards:
        key = (str(reward.get("subject_key", "")), str(reward.get("decision_id", "")))
        if not all(key):
            continue

        current = grouped.get(key)
        is_positive = (
            reward.get("event_type") == positive_event_type
            and float(reward.get("reward", 0.0)) > 0.0
        )
        if current is None or (is_positive and current["reward"] == 0):
            grouped[key] = {
                "reward": 1 if is_positive else 0,
                "event_id": reward.get("event_id", ""),
                "occurred_at": reward.get("occurred_at", ""),
            }
    return grouped


def build_training_rows(
    decisions: list[dict[str, Any]],
    rewards: list[dict[str, Any]],
    *,
    positive_event_type: str = "conversion",
    include_unrewarded_as_zero: bool = False,
) -> list[dict[str, Any]]:
    rewards_by_decision = _reward_by_decision(rewards, positive_event_type)
    rows: list[dict[str, Any]] = []

    for index, decision in enumerate(decisions):
        subject_key = str(decision.get("subject_key", ""))
        decision_id = str(decision.get("decision_id", ""))
        if not subject_key or not decision_id:
            continue

        reward = rewards_by_decision.get((subject_key, decision_id))
        if reward is None and not include_unrewarded_as_zero:
            continue

        selected_offer_id = str(decision.get("selected_offer_id") or decision.get("offer_id") or "")
        action = normalize_legacy_action(resolve_offer_action(selected_offer_id))
        context = decision.get("minimized_context") or {}
        assert_safe_payload(context, path="minimized_context")

        rows.append(
            {
                "row_id": decision.get("request_id") or f"cosmos_{index}",
                "recency": context.get("recency", 0),
                "history_segment": context.get("history_segment", "unknown"),
                "newbie": context.get("newbie", 0),
                "channel": context.get("channel", "Web"),
                "action": action,
                "reward": reward["reward"] if reward is not None else 0,
                "decision_id": decision_id,
                "event_id": reward["event_id"] if reward is not None else "",
                "occurred_at": reward["occurred_at"] if reward is not None else "",
            }
        )
    return rows


def write_training_csv(rows: list[dict[str, Any]], output_file: Path) -> None:
    assert_safe_payload(rows, path="training_rows")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=TRAINING_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def export_events(
    output_file: Path = DEFAULT_OUTPUT_FILE,
    *,
    source_jsonl: Path | None = None,
    include_unrewarded_as_zero: bool = False,
    positive_event_type: str = "conversion",
) -> dict[str, Any]:
    if source_jsonl is not None:
        decisions, rewards = _read_jsonl_events(source_jsonl)
        source = str(source_jsonl)
    else:
        settings = load_settings()
        decisions, rewards = _read_cosmos_items(settings)
        source = settings.azure_cosmos_endpoint

    rows = build_training_rows(
        decisions,
        rewards,
        positive_event_type=positive_event_type,
        include_unrewarded_as_zero=include_unrewarded_as_zero,
    )
    write_training_csv(rows, output_file)
    return {
        "source": source,
        "output_file": str(output_file),
        "decisions_read": len(decisions),
        "rewards_read": len(rewards),
        "training_rows": len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export ECloe Cosmos DB decision/reward events to a training CSV."
    )
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument(
        "--source-jsonl",
        type=Path,
        default=None,
        help="Read local JSONL decision events instead of Cosmos DB.",
    )
    parser.add_argument(
        "--include-unrewarded-as-zero",
        action="store_true",
        help="Include decisions without reward events as reward=0.",
    )
    parser.add_argument(
        "--positive-event-type",
        default="conversion",
        help="Reward event type treated as a positive training outcome.",
    )
    args = parser.parse_args()

    result = export_events(
        output_file=args.output_file,
        source_jsonl=args.source_jsonl,
        include_unrewarded_as_zero=args.include_unrewarded_as_zero,
        positive_event_type=args.positive_event_type,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
