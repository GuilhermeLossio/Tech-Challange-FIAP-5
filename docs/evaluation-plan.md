# Evaluation Plan - ECloe

## Purpose

This document defines how ECloe policies should be evaluated for the Datathon MVP. The focus is a simple, reproducible offline comparison between a deterministic baseline and three adaptive bandit policies.

## Evaluation Layers

| Layer | Goal |
|-------|------|
| Data validation | Confirm Hillstrom action/reward mapping, binary rewards, minimized context, and no blocked columns |
| Offline policy evaluation | Compare Baseline, Epsilon-Greedy, UCB, and Thompson Sampling |
| Golden Set validation | Explain 5 customer examples and the recommended offer for each one |
| MLOps tracking | Log parameters, metrics, and artifacts locally with MLflow |
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

## Golden Set Expectations

The Datathon scope requires a simplified Golden Set with 5 examples. Each case should include:

- customer/context summary;
- eligible offers;
- recommended offer;
- selected policy;
- short explanation of why the recommendation makes sense.

The Golden Set can be generated from the processed dataset or from documented synthetic examples. It should be deterministic for the same seed and configuration.

## Pass and Fail Criteria

A policy passes evaluation when:

- It is reproducible from recorded configuration and data version references.
- It performs better than or equal to the deterministic baseline on the selected primary metric.
- It does not rely on leakage fields or unavailable production-time data.
- It produces interpretable outputs for the Golden Set.
- Its metrics are logged through the planned local MLflow workflow.

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
- MLflow run metadata;
- known limitations and final policy recommendation.
