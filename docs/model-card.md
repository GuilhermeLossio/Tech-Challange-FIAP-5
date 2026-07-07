# Model Card - ECloe Offer Policy

## Overview

ECloe evaluates adaptive decision policies for recommending financial offers in an offline experimentation environment. The current repository includes data processing code and planned policy documentation; it does not yet contain trained production artifacts or executed experiment results.

| Field | Value |
|-------|-------|
| Model family | Multi-armed bandit policy |
| Main candidate policy | Thompson Sampling |
| Comparison policies | Epsilon-Greedy and UCB |
| Control policy | Deterministic baseline |
| Reward type | Binary reward, such as click or conversion |
| Status | MVP design and implementation plan, not production deployed |

## Intended Use

The policy is intended to recommend one eligible offer for a simulated or anonymized customer context in a Datathon MVP. It supports offline evaluation, Golden Set validation, and a future script, notebook, or simple API demo.

The policy is not intended for credit approval, account blocking, product eligibility, fraud decisions, or any decision that creates legal or similarly significant effects without human review.

## Data Assumptions

The factual foundation is the public Kaggle `bank-marketing` dataset by henriqueyamahata. The `duration` column is excluded because it is only known after contact and would create temporal leakage.

The MVP uses three documented simulated offers:

- `credit_limit`
- `personal_loan`
- `cashback_investment`

Direct identifiers, sensitive attributes, income, wealth, and precise location are excluded from the decision policy.

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
| Conversion rate | Measures observed binary reward by offer and policy |
| Cumulative reward | Tracks total successful simulated outcomes |
| Cumulative regret | Estimates the loss against the best available policy |
| Exploration rate | Tracks how often the policy explores uncertain offers |
| Demo latency | Tracks serving performance for a future script or API |
| Operational consumption | Confirms the MVP remains low-cost and easy to run |

## Fairness and Governance

Fairness monitoring is based on synthetic or source-derived segments, not protected real-world groups. The system must not infer or collect gender, race, ethnicity, religion, health data, or other sensitive attributes for policy optimization.

Policy selection requires offline evaluation, metric validation, documented review, and human approval before any production-like use. Privacy assumptions are documented in [`lgpd-plan.md`](lgpd-plan.md), and release controls are documented in [`governance.md`](governance.md).

## Risks and Limitations

| Risk | Mitigation |
|------|------------|
| Offline simulation does not match real customers | Label results as offline/simulated and avoid production claims |
| Reward assumptions favor one offer | Document the simulation logic and compare policies on the same sequence |
| Exploration exposes users unevenly | Monitor exploration rate and exposure by segment |
| Data leakage inflates performance | Exclude post-contact fields such as `duration` |
| Policy becomes stale | Monitor drift and require controlled retraining before promotion |

## Approval Criteria

A policy version should only be selected for the demo when it:

- Performs better than or equal to the deterministic baseline on the selected primary metric.
- Has reproducible configuration and data version references.
- Emits auditable reason codes.
- Is evaluated on the Golden Set.
- Has a documented rollback or fallback path to the baseline.
