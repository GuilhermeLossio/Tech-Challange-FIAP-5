from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.bandits import ACTIONS
from src.data.schemas import MODEL_CONTEXT_COLUMNS
from src.engine.offers import resolve_offer_action
from src.engine.schemas import EngineRequest, LikelihoodEstimate, LikelihoodResponse
from src.engine.validation import validate_engine_request


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_FILE = ROOT_DIR / "data" / "processed" / "hillstrom_processed.csv"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "reports" / "policy_training"
DEFAULT_LIKELIHOOD_MODEL_FILE = DEFAULT_OUTPUT_DIR / "purchase_likelihood_model.json"
DEFAULT_MIN_SAMPLES = 10
DEFAULT_SMOOTHING_ALPHA = 2.0


@dataclass(frozen=True)
class LikelihoodModel:
    version: str
    generated_at: str
    source_file: str
    global_conversion_rate: float
    global_count: int
    action_rates: dict[str, dict[str, float | int]]
    context_rates: dict[str, dict[str, float | int | str]]
    min_samples: int
    smoothing_alpha: float
    context_columns: list[str]

    @classmethod
    def from_json(cls, path: Path) -> "LikelihoodModel":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(**payload)

    def to_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def _smoothed_rate(successes: float, count: int, global_rate: float, alpha: float) -> float:
    return round((successes + (alpha * global_rate)) / (count + alpha), 6)


def _context_key(action: str, values: dict[str, Any]) -> str:
    parts = [f"action={action}"]
    parts.extend(f"{key}={values[key]}" for key in sorted(values))
    return "|".join(parts)


def _row_context(row: pd.Series, columns: list[str]) -> dict[str, Any]:
    return {
        column: None if pd.isna(row[column]) else row[column].item()
        if hasattr(row[column], "item")
        else row[column]
        for column in columns
    }


def train_likelihood_model(
    input_file: Path = DEFAULT_INPUT_FILE,
    output_file: Path = DEFAULT_LIKELIHOOD_MODEL_FILE,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    smoothing_alpha: float = DEFAULT_SMOOTHING_ALPHA,
) -> LikelihoodModel:
    dataframe = pd.read_csv(input_file)
    required_columns = {"action", "reward", *MODEL_CONTEXT_COLUMNS}
    missing = required_columns - set(dataframe.columns)
    if missing:
        raise ValueError(f"Missing required columns for likelihood training: {sorted(missing)}")

    invalid_actions = sorted(set(dataframe["action"].dropna().unique()) - set(ACTIONS))
    if invalid_actions:
        raise ValueError(f"Invalid actions in likelihood training data: {invalid_actions}")

    invalid_rewards = sorted(set(dataframe["reward"].dropna().unique()) - {0, 1})
    if invalid_rewards:
        raise ValueError(f"Invalid rewards in likelihood training data: {invalid_rewards}")

    global_count = int(len(dataframe))
    global_rate = float(dataframe["reward"].mean()) if global_count else 0.0

    action_rates: dict[str, dict[str, float | int]] = {}
    for action in ACTIONS:
        action_rows = dataframe[dataframe["action"] == action]
        count = int(len(action_rows))
        successes = float(action_rows["reward"].sum())
        action_rates[action] = {
            "count": count,
            "successes": int(successes),
            "rate": _smoothed_rate(successes, count, global_rate, smoothing_alpha),
        }

    context_rates: dict[str, dict[str, float | int | str]] = {}
    grouping_levels = [
        ["channel", "history_segment", "newbie"],
        ["channel", "history_segment"],
        ["channel"],
    ]
    for action in ACTIONS:
        action_rows = dataframe[dataframe["action"] == action]
        for columns in grouping_levels:
            for values, group in action_rows.groupby(columns, dropna=False):
                values_tuple = values if isinstance(values, tuple) else (values,)
                context = dict(zip(columns, values_tuple, strict=True))
                key = _context_key(action, context)
                count = int(len(group))
                successes = float(group["reward"].sum())
                context_rates[key] = {
                    "action": action,
                    "columns": ",".join(columns),
                    "count": count,
                    "successes": int(successes),
                    "rate": _smoothed_rate(successes, count, global_rate, smoothing_alpha),
                }

    model = LikelihoodModel(
        version="likelihood-v1",
        generated_at=datetime.now(UTC).isoformat(),
        source_file=str(input_file),
        global_conversion_rate=round(global_rate, 6),
        global_count=global_count,
        action_rates=action_rates,
        context_rates=context_rates,
        min_samples=min_samples,
        smoothing_alpha=smoothing_alpha,
        context_columns=list(MODEL_CONTEXT_COLUMNS),
    )
    model.to_json(output_file)
    return model


class PurchaseLikelihoodService:
    def __init__(self, model: LikelihoodModel) -> None:
        self.model = model

    @classmethod
    def from_file(cls, path: Path = DEFAULT_LIKELIHOOD_MODEL_FILE) -> "PurchaseLikelihoodService":
        return cls(LikelihoodModel.from_json(path))

    def estimate(self, request: EngineRequest) -> LikelihoodResponse:
        validate_engine_request(request)
        estimates = [self._estimate_offer(request.customer_context, offer) for offer in request.eligible_offers]
        warnings = sorted({warning for estimate in estimates for warning in estimate.warnings})
        return LikelihoodResponse(request_id=request.request_id, estimates=estimates, warnings=warnings)

    def _estimate_offer(self, context: dict[str, Any], offer_id: str) -> LikelihoodEstimate:
        action = resolve_offer_action(offer_id)
        candidates = [
            {"channel": context.get("channel"), "history_segment": context.get("history_segment"), "newbie": context.get("newbie")},
            {"channel": context.get("channel"), "history_segment": context.get("history_segment")},
            {"channel": context.get("channel")},
        ]

        for candidate in candidates:
            compact = {key: value for key, value in candidate.items() if value is not None}
            if len(compact) != len(candidate):
                continue
            key = _context_key(action, compact)
            rate = self.model.context_rates.get(key)
            if rate:
                sample_count = int(rate["count"])
                return LikelihoodEstimate(
                    offer_id=offer_id,
                    proxy_action=action,
                    purchase_likelihood=float(rate["rate"]),
                    confidence=self._confidence(sample_count),
                    fallback_level=f"context:{rate['columns']}",
                    sample_count=sample_count,
                    reason_codes=["contextual_conversion_rate"],
                    warnings=self._warnings(sample_count),
                )

        action_rate = self.model.action_rates[action]
        sample_count = int(action_rate["count"])
        if sample_count:
            return LikelihoodEstimate(
                offer_id=offer_id,
                proxy_action=action,
                purchase_likelihood=float(action_rate["rate"]),
                confidence=self._confidence(sample_count),
                fallback_level="action_rate",
                sample_count=sample_count,
                reason_codes=["action_conversion_rate", "context_fallback"],
                warnings=self._warnings(sample_count),
            )

        return LikelihoodEstimate(
            offer_id=offer_id,
            proxy_action=action,
            purchase_likelihood=float(self.model.global_conversion_rate),
            confidence="low",
            fallback_level="global_rate",
            sample_count=int(self.model.global_count),
            reason_codes=["global_conversion_rate", "action_fallback"],
            warnings=["context_or_action_has_limited_evidence"],
        )

    def _confidence(self, sample_count: int) -> str:
        if sample_count >= self.model.min_samples * 5:
            return "high"
        if sample_count >= self.model.min_samples:
            return "medium"
        return "low"

    def _warnings(self, sample_count: int) -> list[str]:
        if sample_count < self.model.min_samples:
            return ["context_or_action_has_limited_evidence"]
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the ECloe purchase likelihood validator.")
    parser.add_argument("--input-file", type=Path, default=DEFAULT_INPUT_FILE)
    parser.add_argument("--output-file", type=Path, default=DEFAULT_LIKELIHOOD_MODEL_FILE)
    parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    parser.add_argument("--smoothing-alpha", type=float, default=DEFAULT_SMOOTHING_ALPHA)
    args = parser.parse_args()

    model = train_likelihood_model(
        input_file=args.input_file,
        output_file=args.output_file,
        min_samples=args.min_samples,
        smoothing_alpha=args.smoothing_alpha,
    )
    print(
        json.dumps(
            {
                "output_file": str(args.output_file),
                "version": model.version,
                "global_conversion_rate": model.global_conversion_rate,
                "global_count": model.global_count,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
