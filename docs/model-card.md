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

The policy is intended to recommend one eligible action for an anonymized ECloe Market and ECloe Pay context. Observed offline evaluation requires logged behavior propensities and terminal outcomes. Synthetic demonstrations support tests and UI flows only; they cannot be used for policy selection or promotion.

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

The purchase-likelihood validator uses smoothed reward estimates from the training split for the outcome model in Doubly Robust evaluation. Policy value is estimated on held-out observed logs with DR as the primary estimator and IPS/SNIPS as diagnostics. Without valid propensity overlap there is no causal guarantee and the result is non-promotable.

## Fairness and Governance

Fairness monitoring is based on synthetic or source-derived segments, not protected real-world groups. The system must not infer or collect gender, race, ethnicity, religion, health data, or other sensitive attributes for policy optimization.

Policy selection requires offline evaluation, metric validation, documented review, and human approval before any production-like use. Privacy assumptions are documented in [`lgpd-plan.md`](lgpd-plan.md), and release controls are documented in [`governance.md`](governance.md).

## Risks and Limitations

| Risk | Mitigation |
|------|------------|
| Offline logs do not have overlap or valid propensities | Exclude invalid rows, report coverage, and keep the runtime on baseline |
| Marketplace signals are over-specific | Aggregate purchase behavior into coarse categories before decisioning |
| Synthetic data is mistaken for observed evidence | Keep `observed_offline` and `synthetic_demo` reports separate; synthetic results cannot promote |
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

## Surface-Specific Recommendation Artifacts

| Artifact | Status | Objective | Serving rule |
|:---|:---|:---|:---|
| Deterministic Market baseline | Implemented | Stable eligible product ordering | Default and final fallback |
| Deterministic Pay baseline | Implemented | Stable eligible benefit ordering | Default and final fallback |
| Market likelihood ranker | Planned for demo | Verified product purchase within 24 hours | Requires 1,000 decisions and 100 positives |
| Pay likelihood ranker | Planned for demo | Verified benefit acceptance in session | Requires 1,000 decisions and 100 positives |
| Adaptive bandit policies | Future | Controlled exploration of eligible candidates | Shadow first, then manually approved canary |

Market and Pay artifacts must have different versions, checksums, evaluation reports, and promotion records. Sex, gender, identifying attributes, raw financial values, and detailed user histories are excluded from both artifacts. See [`recommendation-system.md`](recommendation-system.md) for calculations, reason codes, and limitations.
