# System Card - ECloe

## System Purpose

ECloe is a low-cost adaptive experimentation MVP for recommending next-best eligible actions in an integrated marketplace and digital wallet ecosystem. It combines Kaggle-based data preparation, offline bandit policy evaluation, Golden Set validation, local reports, and a future lightweight demo interface.

## Main Components

| Component | Responsibility |
|-----------|----------------|
| Data preparation | Downloads and processes the Kaggle Hillstrom email-campaign dataset |
| Offline simulator | Uses customer/context rows and binary rewards to compare policies |
| Bandit policies | Compare deterministic baseline, Epsilon-Greedy, UCB, and Thompson Sampling |
| Evaluation layer | Calculates conversion, reward, regret, and exploration metrics |
| Golden Set | Provides 5 explainable customer examples for Demo Day |
| Marketplace-finance demo | Planned app simulation connecting marketplace behavior, wallet context, eligible actions, and rewards |
| Observability and reporting | Uses local reports and lightweight operational metrics |

## Operating Flow

1. Kaggle data is downloaded to `data/raw/`.
2. Processing maps `segment -> action`, maps `conversion -> reward`, and minimizes context fields.
3. The simulator presents customer contexts to each policy.
4. Each policy chooses one simulated eligible marketplace-finance action.
5. The simulator returns a binary reward.
6. Metrics are calculated and logged.
7. The selected policy is demonstrated with the Golden Set.

The visual flow is available in [`decision-flow.svg`](decision-flow.svg).

## Guardrails

- No real customer data is used in the Datathon context.
- No credit, blocking, fraud, or eligibility decision is made by the MVP.
- Eligibility is determined upstream by marketplace, wallet, risk, and compliance rules.
- Raw item-level purchase history must be aggregated before reaching the decision engine.
- Sensitive production decisions would require human review.
- Policy selection requires offline validation before any production-like use.
- Logs must not contain direct identifiers or sensitive attributes.
- Cloud deployment should remain low-consumption unless scale requirements justify more services.

## Expected Failure Modes

| Failure mode | Expected handling |
|--------------|-------------------|
| Missing Kaggle credentials | Fail with a clear setup message |
| No raw CSV file found | Ask the user to download or configure the dataset |
| Blocked field present | Fail validation and remove the field before modeling |
| No eligible offers | Return a no-decision response or deterministic fallback |
| Policy underperforms baseline | Keep the baseline or select another adaptive policy |
| Reward assumptions are unclear | Document the simulation logic and seed |

## Monitoring

MVP monitoring should focus on conversion rate, cumulative reward, cumulative regret, exploration rate, demo latency, and local report completeness. Future cloud monitoring can add API error rate, event write failures, and policy version observability.

## Operational Boundaries

ECloe is not production-ready in the current repository state. A real deployment would require security review, legal review, data protection approval, incident response testing, and regulated financial suitability validation.
