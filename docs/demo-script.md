# Demo Script - ECloe

## Goal

Use this script to present ECloe as a practical ML Engineering MVP for adaptive financial offer experimentation. The demo should emphasize low-cost execution, offline evaluation, and a working recommendation flow rather than enterprise infrastructure.

## Suggested Flow

### 1. Business Problem

Digital financial channels often choose offers using static rules or long A/B tests. ECloe reframes the problem as adaptive experimentation so the system can learn from each interaction while preserving governance and auditability.

### 2. Dataset and Preparation

Show that the project uses the public Kaggle `bank-marketing` dataset. Explain that `duration` is removed because it would leak post-contact information, and that `y` is treated as the observed conversion signal.

### 3. Stage 3 Algorithm Strategy

Explain that the algorithms are compared, not merged:

- Deterministic baseline as the control policy.
- Epsilon-Greedy as a simple adaptive policy.
- UCB as an optimistic adaptive policy.
- Thompson Sampling as the main candidate policy.

The same customer order and reward assumptions are used for all policies so the comparison is fair.

### 4. Decision Flow

Show [`decision-flow.svg`](decision-flow.svg). Explain that a future channel or demo interface sends minimized context and eligible offers, the active policy returns one offer with reason codes, and later reward events update evaluation metrics.

### 5. Golden Set

Show 5 customer examples with:

- short context;
- recommended offer;
- selected policy;
- short business explanation.

This is the clearest Demo Day evidence that the recommendation flow is understandable.

### 6. MLOps and Metrics

Use [`evaluation-plan.md`](evaluation-plan.md) to describe conversion rate, cumulative reward, cumulative regret, exploration rate, and local MLflow tracking. The goal is to prove the evaluation loop, not to claim production performance.

### 7. Low-Cost Architecture

Show [`azure-architecture-flow.svg`](azure-architecture-flow.svg), but separate the MVP from future enterprise architecture.

For the MVP, explain:

- local Python execution first;
- optional script, notebook, or lightweight API;
- Azure App Service or Container Apps only if a cloud demo is needed;
- Blob Storage for artifacts;
- Cosmos DB Serverless or small PostgreSQL for events;
- Application Insights for basic operational telemetry.

### 8. Limitations

Close with the main limitations:

- The dataset is public and not real customer data.
- Offers and reward assumptions are simulated for the MVP.
- Offline results are not production evidence.
- Regulated production use would require security, privacy, legal, and model risk reviews.

## Suggested Closing

ECloe demonstrates how a financial recommendation engine can be designed as a practical, low-consumption ML Engineering MVP with offline evaluation, explainability, and governance from the start.
