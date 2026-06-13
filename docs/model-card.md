# Model Card - ECloe Offer Policy

## Overview

ECloe uses adaptive decision policies to select financial offers in a synthetic experimentation environment. The current repository documents the target behavior; it does not contain a trained production model or live experiment results.

| Field | Value |
|-------|-------|
| Model family | Contextual multi-armed bandit policy |
| Main policy | Thompson Sampling |
| Comparison policy | Nilos-UCB |
| Control policy | Deterministic historical best arm |
| Reward type | Binary reward, such as click or conversion |
| Status | Planned and documented, not production deployed |

## Intended Use

The policy is intended to recommend one eligible offer for a synthetic customer session, using minimized behavioral and contextual features. It is designed for ML Engineering demonstration, offline evaluation, and future API implementation.

The policy is not intended for credit approval, account blocking, product eligibility, fraud decisions, or any decision that creates legal or similarly significant effects without human review.

## Data Assumptions

The factual foundation is the public Kaggle `bank-marketing` dataset. Synthetic enrichment is planned to create offer catalogs, decision events, and delayed reward examples.

Direct identifiers, sensitive attributes, income, wealth, and precise location are excluded from the decision policy. The `duration` column from the Kaggle dataset is excluded because it is only known after contact and would create temporal leakage.

## Inputs and Outputs

Expected inputs:

- `customer_context.segment`
- `customer_context.channel`
- `customer_context.risk_band`
- `eligible_offers`
- `request_id`

Expected outputs:

- `decision_id`
- `offer_id`
- `policy`
- `policy_version`
- `reason_codes`

The canonical payloads are documented in [`api-contract.md`](api-contract.md).

## Metrics

| Metric | Purpose |
|--------|---------|
| Conversion rate | Measures observed reward by offer and segment |
| Cumulative regret | Estimates the loss against the best available policy |
| Exploration ratio | Tracks how often the policy explores uncertain offers |
| Reward latency | Measures time between decision and reward observation |
| Fairness index | Compares exposure across synthetic segments |
| API latency p95 | Tracks serving performance for the future API |

## Fairness and Governance

Fairness monitoring is based on synthetic segments, not protected real-world groups. The system must not infer or collect gender, race, ethnicity, religion, health data, or other sensitive attributes for policy optimization.

Policy promotion requires offline evaluation, metric validation, documented review, and human approval. Privacy assumptions are documented in [`lgpd-plan.md`](lgpd-plan.md), and release controls are documented in [`governance.md`](governance.md).

## Risks and Limitations

| Risk | Mitigation |
|------|------------|
| Synthetic behavior does not match real customers | Label results as synthetic and avoid production claims |
| Delayed rewards distort policy learning | Separate immediate events from delayed reward processing |
| Exploration exposes users unevenly | Monitor exploration ratio and exposure by segment |
| Data leakage inflates offline performance | Exclude post-contact fields such as `duration` |
| Policy becomes stale | Monitor drift and require controlled retraining |

## Approval Criteria

A policy version should only be promoted when it:

- Beats the deterministic baseline on primary offline metrics.
- Does not degrade fairness index beyond the documented threshold for the experiment.
- Produces auditable reason codes.
- Has reproducible artifacts, configuration, and data version references.
- Has a documented rollback path.

