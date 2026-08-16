from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.core.config import Settings, load_settings
from src.market.application.catalog_loader import load_catalog
from src.recommendation.privacy import assert_safe_payload, neutralize_category

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "src" / "recommendation" / "schema.sql"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "recommendation_seed"
DEFAULT_SUBJECTS = 250
DEFAULT_MARKET_INTERACTIONS = 10_000
DEFAULT_PAY_INTERACTIONS = 3_000
DEFAULT_SEED = 42
PAY_CANDIDATES = ("cashback_recurring_purchase", "savings_goal", "financial_education")


@dataclass(frozen=True)
class SeedBundle:
    seed_run_id: str
    seed: int
    subjects: tuple[dict[str, Any], ...]
    interactions: tuple[dict[str, Any], ...]
    checksum: str


def build_seed_bundle(
    settings: Settings,
    *,
    subject_count: int = DEFAULT_SUBJECTS,
    market_interactions: int = DEFAULT_MARKET_INTERACTIONS,
    pay_interactions: int = DEFAULT_PAY_INTERACTIONS,
    seed: int = DEFAULT_SEED,
) -> SeedBundle:
    if subject_count <= 0 or market_interactions < 0 or pay_interactions < 0:
        raise ValueError("Synthetic seed counts must be non-negative and include subjects.")
    catalog = load_catalog(settings.ecloe_market_catalog_path)
    product_ids = [product.product_id for product in catalog.products if product.active]
    categories = sorted({neutralize_category(product.category_id) for product in catalog.products})
    if not product_ids:
        raise ValueError("The ECloe Market catalog has no active products for synthetic seeding.")
    rng = random.Random(seed)
    seed_run_id = f"seed_recommendation_{seed}_{subject_count}_{market_interactions}_{pay_interactions}"
    subjects = tuple(
        _subject(seed_run_id, index, categories, rng) for index in range(subject_count)
    )
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    interactions = []
    for index in range(market_interactions):
        interactions.append(
            _interaction(
                seed_run_id,
                subjects[index % len(subjects)]["subject_key"],
                "market",
                product_ids[index % len(product_ids)],
                index,
                started_at,
                rng,
            )
        )
    for index in range(pay_interactions):
        interactions.append(
            _interaction(
                seed_run_id,
                subjects[index % len(subjects)]["subject_key"],
                "pay",
                PAY_CANDIDATES[index % len(PAY_CANDIDATES)],
                market_interactions + index,
                started_at,
                rng,
            )
        )
    payload = {"subjects": subjects, "interactions": interactions}
    assert_safe_payload(payload)
    checksum = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return SeedBundle(seed_run_id, seed, subjects, tuple(interactions), checksum)


def write_seed_bundle(bundle: SeedBundle, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    subjects_file = output_dir / "feature_snapshots.jsonl"
    interactions_file = output_dir / "synthetic_interactions.jsonl"
    subjects_file.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in bundle.subjects),
        encoding="utf-8",
    )
    interactions_file.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in bundle.interactions),
        encoding="utf-8",
    )
    manifest = {
        "seed_run_id": bundle.seed_run_id,
        "seed": bundle.seed,
        "subject_count": len(bundle.subjects),
        "market_interaction_count": sum(
            item["surface"] == "market" for item in bundle.interactions
        ),
        "pay_interaction_count": sum(item["surface"] == "pay" for item in bundle.interactions),
        "checksum": bundle.checksum,
        "data_origin": "synthetic_seed",
        "files": {
            "feature_snapshots": str(subjects_file),
            "synthetic_interactions": str(interactions_file),
        },
    }
    manifest_file = output_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {**manifest["files"], "manifest": str(manifest_file)}


def apply_seed_to_azure_sql(bundle: SeedBundle, settings: Settings) -> None:
    from sqlalchemy import text

    from scripts.init_ecloe_market_sql import (
        _engine_with_entra_token,
        _entra_access_token,
        _resolve_odbc_driver,
    )

    driver = _resolve_odbc_driver(settings.ecloe_pay_sql_driver)
    token = _entra_access_token(settings.ecloe_pay_sql_auth_mode)
    engine = _engine_with_entra_token(settings, token, driver)
    with engine.begin() as connection:
        for statement in re.split(r"(?im)^\s*GO\s*$", SCHEMA_FILE.read_text(encoding="utf-8")):
            if statement.strip():
                connection.exec_driver_sql(statement)
        market_count = sum(item["surface"] == "market" for item in bundle.interactions)
        pay_count = len(bundle.interactions) - market_count
        connection.execute(
            text(
                """
                IF NOT EXISTS (SELECT 1 FROM ecloe_features.seed_runs WHERE seed_run_id = :seed_run_id)
                INSERT INTO ecloe_features.seed_runs (
                    seed_run_id, seed_value, subject_count, market_interaction_count,
                    pay_interaction_count, payload_checksum, data_origin
                ) VALUES (
                    :seed_run_id, :seed_value, :subject_count, :market_count,
                    :pay_count, :payload_checksum, N'synthetic_seed'
                )
                """
            ),
            {
                "seed_run_id": bundle.seed_run_id,
                "seed_value": bundle.seed,
                "subject_count": len(bundle.subjects),
                "market_count": market_count,
                "pay_count": pay_count,
                "payload_checksum": bundle.checksum,
            },
        )
        for subject in bundle.subjects:
            for surface in ("market", "pay"):
                connection.execute(
                    text(
                        """
                        IF NOT EXISTS (
                            SELECT 1 FROM ecloe_features.feature_snapshots
                            WHERE snapshot_id = :snapshot_id
                        )
                        INSERT INTO ecloe_features.feature_snapshots (
                            snapshot_id, seed_run_id, subject_key, surface, features_json
                        ) VALUES (
                            :snapshot_id, :seed_run_id, :subject_key, :surface, :features_json
                        )
                        """
                    ),
                    {
                        "snapshot_id": f"snap_{surface}_{subject['subject_key']}",
                        "seed_run_id": bundle.seed_run_id,
                        "subject_key": subject["subject_key"],
                        "surface": surface,
                        "features_json": json.dumps(subject[surface], sort_keys=True),
                    },
                )
        for item in bundle.interactions:
            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM ecloe_features.synthetic_interactions WHERE event_id = :event_id
                    )
                    INSERT INTO ecloe_features.synthetic_interactions (
                        event_id, seed_run_id, subject_key, decision_id, surface,
                        candidate_id, position, event_type, terminal, reward, occurred_at
                    ) VALUES (
                        :event_id, :seed_run_id, :subject_key, :decision_id, :surface,
                        :candidate_id, :position, :event_type, :terminal, :reward, :occurred_at
                    )
                    """
                ),
                item,
            )


def _subject(seed_run_id: str, index: int, categories: list[str], rng: random.Random) -> dict[str, Any]:
    digest = hashlib.sha256(f"{seed_run_id}:subject:{index}".encode()).hexdigest()[:24]
    category = categories[index % len(categories)] if categories else "uncategorized"
    return {
        "subject_key": f"sub_synthetic_{digest}",
        "data_origin": "synthetic_seed",
        "market": {
            "channel": rng.choice(["Web", "Phone", "Multichannel"]),
            "newbie": int(index % 5 == 0),
            "recency_band": rng.choice(["recent", "established", "dormant"]),
            "frequency_band": rng.choice(["low", "medium", "high"]),
            "history_segment": rng.choice(["low", "medium", "high"]),
            "category_affinities": [category],
            "cart_size_band": rng.choice(["empty", "small", "medium"]),
            "cart_value_band": rng.choice(["low", "medium", "high"]),
        },
        "pay": {
            "channel": rng.choice(["Web", "Phone", "Multichannel"]),
            "newbie": int(index % 5 == 0),
            "recency_band": rng.choice(["recent", "established", "dormant"]),
            "frequency_band": rng.choice(["low", "medium", "high"]),
            "history_segment": rng.choice(["low", "medium", "high"]),
            "wallet_engagement_band": rng.choice(["low", "medium", "high"]),
            "benefit_response_band": rng.choice(["unknown", "low", "high"]),
            "savings_goal_active": bool(index % 2),
        },
    }


def _interaction(
    seed_run_id: str,
    subject_key: str,
    surface: str,
    candidate_id: str,
    index: int,
    started_at: datetime,
    rng: random.Random,
) -> dict[str, Any]:
    probability = rng.random()
    if surface == "market":
        event_type = "purchase" if probability < 0.08 else "expired"
    else:
        event_type = "acceptance" if probability < 0.12 else "rejection"
    terminal = True
    reward = 1.0 if event_type in {"purchase", "acceptance"} else 0.0
    suffix = hashlib.sha256(f"{seed_run_id}:{surface}:{index}".encode()).hexdigest()[:20]
    return {
        "event_id": f"evt_synthetic_{suffix}",
        "seed_run_id": seed_run_id,
        "subject_key": subject_key,
        "decision_id": f"dec_synthetic_{suffix}",
        "surface": surface,
        "candidate_id": candidate_id,
        "position": 1,
        "event_type": event_type,
        "terminal": terminal,
        "reward": reward,
        "occurred_at": (started_at + timedelta(minutes=index)).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic ECloe recommendation seed.")
    parser.add_argument("--subjects", type=int, default=DEFAULT_SUBJECTS)
    parser.add_argument("--market-interactions", type=int, default=DEFAULT_MARKET_INTERACTIONS)
    parser.add_argument("--pay-interactions", type=int, default=DEFAULT_PAY_INTERACTIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--apply-azure-sql", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    bundle = build_seed_bundle(
        settings,
        subject_count=args.subjects,
        market_interactions=args.market_interactions,
        pay_interactions=args.pay_interactions,
        seed=args.seed,
    )
    files = write_seed_bundle(bundle, args.output_dir)
    if args.apply_azure_sql:
        apply_seed_to_azure_sql(bundle, settings)
    print(
        json.dumps(
            {
                "seed_run_id": bundle.seed_run_id,
                "seed": bundle.seed,
                "subject_count": len(bundle.subjects),
                "interaction_count": len(bundle.interactions),
                "checksum": bundle.checksum,
                "files": files,
                "azure_applied": args.apply_azure_sql,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
