# Evaluation Plan - ECloe

## Purpose

This document defines how ECloe policies should be evaluated for the Datathon MVP. The focus is a simple, reproducible offline comparison between a deterministic baseline and three adaptive bandit policies.

## Evaluation Layers

| Layer | Goal |
|-------|------|
| Data validation | Confirm Hillstrom action/reward mapping, binary rewards, minimized context, and no blocked columns |
| Offline policy evaluation | Compare Baseline, Epsilon-Greedy, UCB, and Thompson Sampling with `python -m src.evaluation.run` |
| Golden Set validation | Explain 5 customer examples and the recommended offer for each one |
| Local reporting | Write deterministic metrics and policy artifacts under `reports/policy_training/` |
| Operational review | Confirm the demo remains lightweight and executable locally |

## Primary Metrics

| Metric | Interpretation |
|--------|----------------|
| Conversion rate | Higher is better when measured on the same simulated cohort |
| Cumulative reward | Higher indicates more successful simulated recommendations |
| Cumulative regret | Lower indicates better offer selection over time |
| Exploration rate | Must remain explainable and aligned with the policy strategy |
| Demo latency | The script, notebook, or API should respond quickly enough for Demo Day |
| Operational consumption | The MVP should avoid unnecessary cloud services and heavy infrastructure |

## Golden Set

The Golden Set contains 5 deterministic examples for Demo Day explanation. Each case includes:

- customer/context summary;
- eligible offers;
- recommended offer;
- selected policy;
- short explanation of why the recommendation makes sense.

The current artifact is generated from the processed dataset and is deterministic for the same seed and configuration.

## Pass and Fail Criteria

A policy passes evaluation when:

- It is reproducible from recorded configuration and data version references.
- It performs better than or equal to the deterministic baseline on the selected primary metric.
- It does not rely on leakage fields or unavailable production-time data.
- It produces interpretable outputs for the Golden Set.
- Its metrics are written to the local policy training reports.

A policy fails evaluation when:

- It relies on blocked fields such as direct identifiers, raw monetary `history`, `zip_code`, income, or wealth.
- It cannot be reproduced.
- It materially worsens reward or regret versus the baseline without a clear trade-off.
- It lacks a documented reward update strategy.
- It cannot support the Demo Day recommendation flow.

## Reporting Outputs

Each evaluation run should produce:

- policy name and configuration;
- dataset source and processing version;
- metric table by policy and offer;
- cumulative reward and regret summary;
- Golden Set recommendations;
- local policy report metadata;
- known limitations and final policy recommendation.

The implemented training workflow is documented in [`training-workflow.md`](training-workflow.md).

Use `python -m src.evaluation.run --prepare-data` when the local processed dataset is missing. Use `--max-rows` for notebook checks or low-consumption experiments.

## Recommendation v2 Evaluation

Status: **Planned for demo**.

Market and Pay are evaluated independently using temporal splits. Required metrics are verified conversion or acceptance, Brier score and calibration, NDCG@K where applicable, candidate coverage, exposure concentration, cumulative regret, and exploration rate. Eligibility violations, out-of-stock selections, and blocked fields must remain zero.

Promotion requires at least 1,000 decisions and 100 positive outcomes per surface, a non-regressing 95 percent bootstrap interval on the primary objective, all safety guardrails, and manual approval. Shadow comparisons measure implementation stability and coverage, not causal uplift. See [`recommendation-system.md`](recommendation-system.md).
