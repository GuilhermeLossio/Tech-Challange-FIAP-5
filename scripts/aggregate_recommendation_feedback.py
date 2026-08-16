from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.core.config import load_settings
from src.recommendation.feedback import canonical_event, events_from_engine_records
from src.recommendation.models import Surface
from src.recommendation.pipeline import build_surface_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate recommendation feedback into surface artifacts.")
    parser.add_argument("--events", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=Path("reports/recommendation"))
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.events is not None:
        events = [
            canonical_event(json.loads(line))
            for line in args.events.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        from scripts.export_cosmos_events_for_training import _read_cosmos_items

        decisions, rewards = _read_cosmos_items(load_settings())
        events = list(events_from_engine_records(decisions, rewards))
    result = {}
    for surface in (Surface.market, Surface.pay):
        output = args.output_root / surface.value / args.run_id
        result[surface.value] = build_surface_run(
            events,
            output_dir=output,
            surface=surface,
            run_id=args.run_id,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
