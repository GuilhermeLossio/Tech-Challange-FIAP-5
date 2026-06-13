# Data Generation Plan - ECloe

## Purpose

This document describes the planned synthetic data generation approach for ECloe. The current repository does not include generated datasets; this plan defines the intended method for future implementation and reproducible evaluation.

## Source Dataset

The factual seed is the public Kaggle `bank-marketing` dataset by henriqueyamahata. It is used because it resembles banking campaign interactions and contains conversion-like outcomes suitable for offline experimentation.

The `duration` column must be removed before modeling because it is known only after contact and would create temporal leakage.

## Synthetic Enrichment Strategy

Synthetic enrichment should create a controlled offer experimentation layer on top of the processed source data:

- Offer catalog with synthetic `offer_id`, category, eligibility constraints, and expected reward assumptions.
- Session contexts with synthetic segment, channel, and risk band.
- Decision events containing `request_id`, `decision_id`, selected `offer_id`, policy, version, and reason codes.
- Reward events containing `decision_id`, `event_type`, `reward`, and `occurred_at`.
- Delayed reward records for conversions that arrive after the initial interaction.

## Planned Entities

| Entity | Expected file | Description |
|--------|---------------|-------------|
| Processed customer contexts | `data/processed/` | Cleaned source-derived rows without leakage fields |
| Offer catalog | `data/synthetic_enrichment/offer_catalog.json` | Synthetic offers and eligibility metadata |
| Offer events | `data/synthetic_enrichment/offer_events.jsonl` | Synthetic impressions and decisions |
| Delayed rewards | `data/synthetic_enrichment/delayed_rewards.jsonl` | Reward events arriving after the decision |
| Golden set | `data/golden_set/evaluation_cases.jsonl` | Deterministic cases for policy and API validation |

These paths are target paths and are not present in the current documentation-only repository.

## Reproducibility Defaults

- Use a fixed seed, initially `42`, for generated examples.
- Store generation configuration with each output batch.
- Record source dataset version and processing date.
- Keep generated data deterministic for the same seed and configuration.
- Do not introduce direct identifiers or protected attributes.

## Validation Checks

Generated data should pass these checks before use:

- No direct identifiers such as name, national taxpayer ID, email, or phone number.
- No sensitive attributes such as gender, race, religion, or health data.
- No leakage columns such as `duration`.
- Every decision event has a valid `decision_id`.
- Every reward event references a known `decision_id`.
- Every selected `offer_id` exists in the offer catalog.
- Reward values are within the documented reward range.
- Segment exposure can be calculated for fairness monitoring.

## Limitations

Synthetic data is useful for demonstration and engineering validation, but it does not prove real-world financial performance. Results derived from this data must be labeled as synthetic and must not be presented as production evidence.

