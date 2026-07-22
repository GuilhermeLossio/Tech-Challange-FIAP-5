from __future__ import annotations

from dataclasses import dataclass

from src.core.config import load_settings


@dataclass(frozen=True)
class AzureDataLayout:
    storage_containers: tuple[str, ...]
    cosmos_database: str
    cosmos_containers: tuple[str, ...]
    cosmos_auth_mode: str
    decision_event_ttl_seconds: int


def get_azure_data_layout() -> AzureDataLayout:
    settings = load_settings()
    return AzureDataLayout(
        storage_containers=(
            settings.azure_blob_container_raw,
            settings.azure_blob_container_processed,
        ),
        cosmos_database=settings.azure_cosmos_database,
        cosmos_containers=(
            settings.azure_cosmos_container_decisions,
            settings.azure_cosmos_container_rewards,
            settings.azure_cosmos_container_policies,
        ),
        cosmos_auth_mode=settings.azure_cosmos_auth_mode,
        decision_event_ttl_seconds=settings.decision_event_ttl_seconds,
    )
