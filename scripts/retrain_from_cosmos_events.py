from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.export_cosmos_events_for_training import (  # noqa: E402
    DEFAULT_OUTPUT_FILE,
    export_events,
)
from src.evaluation.run import DEFAULT_OUTPUT_DIR, DEFAULT_SEED, run_evaluation  # noqa: E402

DEFAULT_MIN_TRAINING_ROWS = 2


def retrain_from_events(
    *,
    export_file: Path = DEFAULT_OUTPUT_FILE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    source_jsonl: Path | None = None,
    include_unrewarded_as_zero: bool = False,
    positive_event_type: str = "conversion",
    max_rows: int | None = None,
    seed: int = DEFAULT_SEED,
    min_training_rows: int = DEFAULT_MIN_TRAINING_ROWS,
) -> dict[str, Any]:
    export_result = export_events(
        output_file=export_file,
        source_jsonl=source_jsonl,
        include_unrewarded_as_zero=include_unrewarded_as_zero,
        positive_event_type=positive_event_type,
    )

    training_rows = int(export_result["training_rows"])
    if training_rows < min_training_rows:
        raise ValueError(
            "Not enough reusable decision/reward rows for training: "
            f"{training_rows} exported, minimum is {min_training_rows}. "
            "Create decisions with matching reward events first, or rerun with "
            "--include-unrewarded-as-zero for demo-only experiments."
        )

    training_result = run_evaluation(
        input_file=export_file,
        output_dir=output_dir,
        seed=seed,
        max_rows=max_rows,
    )

    return {
        "export": export_result,
        "training": training_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Cosmos DB decision/reward events and run ECloe training from them."
    )
    parser.add_argument("--export-file", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
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
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--min-training-rows", type=int, default=DEFAULT_MIN_TRAINING_ROWS)
    args = parser.parse_args()

    result = retrain_from_events(
        export_file=args.export_file,
        output_dir=args.output_dir,
        source_jsonl=args.source_jsonl,
        include_unrewarded_as_zero=args.include_unrewarded_as_zero,
        positive_event_type=args.positive_event_type,
        max_rows=args.max_rows,
        seed=args.seed,
        min_training_rows=args.min_training_rows,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
