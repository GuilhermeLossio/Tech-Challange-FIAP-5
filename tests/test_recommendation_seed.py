from __future__ import annotations

import json

from scripts.seed_recommendation_data import build_seed_bundle, write_seed_bundle
from src.core.config import load_settings
from src.recommendation.privacy import BLOCKED_FEATURE_NAMES, normalize_feature_name


def _keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield normalize_feature_name(str(key))
            yield from _keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _keys(nested)


def test_seed_is_deterministic_and_contains_only_pseudonymous_aggregates(tmp_path) -> None:
    settings = load_settings(use_env_file=False)

    first = build_seed_bundle(
        settings,
        subject_count=10,
        market_interactions=40,
        pay_interactions=20,
        seed=42,
    )
    second = build_seed_bundle(
        settings,
        subject_count=10,
        market_interactions=40,
        pay_interactions=20,
        seed=42,
    )

    assert first.checksum == second.checksum
    assert first.subjects == second.subjects
    assert first.interactions == second.interactions
    assert len({row["subject_key"] for row in first.subjects}) == 10
    assert not (set(_keys(first.subjects)) & BLOCKED_FEATURE_NAMES)

    files = write_seed_bundle(first, tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_origin"] == "synthetic_seed"
    assert manifest["market_interaction_count"] == 40
    assert manifest["pay_interaction_count"] == 20
    assert manifest["checksum"] == first.checksum
    assert set(files) == {"feature_snapshots", "synthetic_interactions", "manifest"}


def test_seed_uses_stable_unique_event_and_decision_ids() -> None:
    bundle = build_seed_bundle(
        load_settings(use_env_file=False),
        subject_count=5,
        market_interactions=25,
        pay_interactions=10,
        seed=42,
    )

    assert len({item["event_id"] for item in bundle.interactions}) == 35
    assert len({item["decision_id"] for item in bundle.interactions}) == 35
    assert {item["surface"] for item in bundle.interactions} == {"market", "pay"}
    assert all(item["data_origin"] == "synthetic_seed" for item in bundle.subjects)

