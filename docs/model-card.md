# Model Card - ECloe Offer Policy

## Overview

ECloe evaluates adaptive decision policies for recommending eligible marketplace-finance actions in an offline experimentation environment. The product framing uses ECloe Market for commerce behavior, ECloe Pay for wallet context and eligible actions, and ECloe Engine for policy selection. The current repository includes data processing code, implemented offline policy simulation, local reports, and policy documentation. It does not contain production-trained artifacts.

| Field | Value |
|-------|-------|
| Model family | Multi-armed bandit policy |
| Main candidate policy | Thompson Sampling |
| Comparison policies | Epsilon-Greedy and UCB |
| Control policy | Deterministic baseline |
| Reward type | Binary reward, such as click or conversion |
| Status | Local offline evaluation, purchase-likelihood validation, and FastAPI serving implemented; not production deployed |

## Intended Use

The policy is intended to recommend one eligible action for a simulated or anonymized ECloe Market and ECloe Pay context in a Datathon MVP. It supports offline evaluation, Golden Set validation, notebooks, and a future simple API or demo app.

The policy is not intended for credit approval, account blocking, product eligibility, fraud decisions, product pricing, or any decision that creates legal or similarly significant effects without human review.

## Data Assumptions

The factual foundation is the public Kaggle Hillstrom email-campaign dataset by bofulee. The processed dataset maps `segment` to the observed action and `conversion` to the binary reward. In the product narrative, this is a proxy for marketplace behavior, digital wallet context, eligible action, and observed reward. Raw monetary `history` and `zip_code` are excluded from the modeling dataset for minimization.

The MVP can map campaign actions to simulated marketplace-finance actions such as:

- `cashback_recurring_purchase`
- `savings_goal`
- `financial_education`
- `account_upgrade`
- `installment_education`

Direct identifiers, sensitive attributes, income, wealth, precise location, raw account balance, detailed credit score, and raw item-level purchase history are excluded from the decision policy.

## Inputs and Outputs

Expected inputs:

- `customer_context.channel`
- `customer_context.history_segment`
- `customer_context.newbie`
- `eligible_offers`
- `request_id`

Expected outputs:

- `decision_id`
- `created_at`
- `offer_id`
- `purchase_likelihood`
- `policy`
- `policy_version`
- `artifact_schema`
- `artifact_version`
- `artifact_checksum`
- `artifact_status`
- `reason_codes`

The canonical payloads are documented in [`api-contract.md`](api-contract.md).
Persisted decision events use a pseudonymized `subject_key`, minimized context, artifact hash, and optional idempotency key for duplicate suppression.

## Metrics

| Metric | Purpose |
|--------|---------|
| Conversion rate | Measures observed binary reward by offer and policy |
| Cumulative reward | Tracks total successful simulated outcomes |
| Cumulative regret | Estimates the loss against the best available policy |
| Exploration rate | Tracks how often the policy explores uncertain offers |
| Demo latency | Tracks serving performance for a future script or API |
| Operational consumption | Confirms the MVP remains low-cost and easy to run |

The purchase-likelihood validator uses smoothed offline conversion rates by action and available context. It is intentionally lightweight and should be interpreted as simulated propensity evidence, not as a production prediction model.

## Fairness and Governance

Fairness monitoring is based on synthetic or source-derived segments, not protected real-world groups. The system must not infer or collect gender, race, ethnicity, religion, health data, or other sensitive attributes for policy optimization.

Policy selection requires offline evaluation, metric validation, documented review, and human approval before any production-like use. Privacy assumptions are documented in [`lgpd-plan.md`](lgpd-plan.md), and release controls are documented in [`governance.md`](governance.md).

## Risks and Limitations

| Risk | Mitigation |
|------|------------|
| Offline simulation does not match real customers | Label results as offline/simulated and avoid production claims |
| Marketplace signals are over-specific | Aggregate purchase behavior into coarse categories before decisioning |
| Reward assumptions favor one offer | Document the simulation logic and compare policies on the same sequence |
| Exploration exposes users unevenly | Monitor exploration rate and exposure by segment |
| Blocked or over-specific fields inflate performance or privacy risk | Exclude direct identifiers, raw monetary `history`, `zip_code`, income, and wealth |
| Policy becomes stale | Monitor drift and require controlled retraining before promotion |

## Approval Criteria

A policy version should only be selected for the demo when it:

- Performs better than or equal to the deterministic baseline on the selected primary metric.
- Has reproducible configuration and data version references.
- Emits auditable reason codes.
- Is evaluated on the Golden Set.
- Has a documented rollback or fallback path to the baseline.

The local training workflow is documented in [`training-workflow.md`](training-workflow.md).
