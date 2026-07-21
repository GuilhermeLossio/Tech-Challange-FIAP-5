# Data Generation Plan - ECloe

## Purpose

This document defines the lightweight synthetic layer needed for ECloe's Datathon MVP. The project should only generate the minimum extra data required to compare policies and demonstrate recommendations.

## Source Dataset

The factual seed is the public Kaggle `kevin-hillstrom-minethatdata-e-mailanalytics` dataset by bofulee. It contains randomized email campaign actions and conversion outcomes suitable for offline experimentation.

The processed modeling dataset maps `segment` into the observed action and `conversion` into the binary reward. It keeps coarse campaign context such as `history_segment`, while excluding raw monetary `history` and `zip_code` from the policy input.

## Synthetic Offer Layer

The MVP uses three documented offers:

| Offer ID | Description |
|----------|-------------|
| `cashback_recurring_purchase` | Cashback incentive for recurring marketplace purchase behavior |
| `savings_goal` | Wallet savings goal or account benefit |
| `financial_education` | Educational action for safer wallet or installment usage |

Synthetic generation should only add what the source dataset does not contain:

- offer catalog with stable `offer_id` values;
- deterministic reward assumptions per segment or context;
- Golden Set examples for 5 customer scenarios;
- optional decision and reward event files for evaluation reporting.

## Planned Entities

| Entity | Expected file | Description |
|--------|---------------|-------------|
| Processed customer contexts | `data/processed/hillstrom_processed.csv` | Cleaned source-derived rows with minimized context, action, and reward fields |
| Offer catalog | `data/processed/offer_catalog.json` | Three synthetic MVP offers |
| Simulation results | `reports/` | Policy metrics and comparison outputs |
| Purchase likelihood artifact | `reports/policy_training/purchase_likelihood_model.json` | Smoothed offline conversion-rate validator for the local API |
| Golden Set | `data/golden_set/evaluation_cases.jsonl` | Five deterministic examples for policy explanation |

These paths are target outputs for the next implementation stages.

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
- No blocked columns such as direct identifiers, raw monetary `history`, `zip_code`, income, or wealth.
- Every selected `offer_id` exists in the offer catalog.
- Reward values are binary or within the documented reward range.
- Segment exposure can be calculated for evaluation.

## Limitations

Synthetic offer and reward data is useful for demonstration and engineering validation, but it does not prove real-world financial performance. Results derived from this data must be labeled as offline or simulated and must not be presented as production evidence.
