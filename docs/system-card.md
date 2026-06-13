# System Card - ECloe

## System Purpose

ECloe is a documented target system for adaptive offer experimentation in digital financial channels. It combines a Decision API, multi-armed bandit policies, reward tracking, MLOps controls, observability, governance, and an explainable LLM assistant named Cloe.

The repository is currently documentation-first. The described runtime services, datasets, and pipelines are target components for future implementation.

## Main Components

| Component | Responsibility |
|-----------|----------------|
| Decision API | Receives context, validates the contract, and returns the selected offer |
| Bandit service | Applies Thompson Sampling, Nilos-UCB, or deterministic baseline policy |
| Reward tracker | Records click, conversion, and delayed reward events |
| MLOps pipeline | Trains, evaluates, versions, and promotes policy versions |
| Cloe assistant | Explains decisions and summarizes experiments using RAG |
| Observability layer | Tracks latency, errors, drift, regret, conversion, and fairness |

## Operating Flow

1. A channel sends minimized context and eligible offers to the Decision API.
2. The Decision API validates the request and calls the active policy.
3. The Bandit service returns one offer and reason codes.
4. The decision is logged with policy and version metadata.
5. Later reward events are attached to the original `decision_id`.
6. Offline evaluation recalculates metrics and informs future policy releases.

The visual flow is available in [`decision-flow.svg`](decision-flow.svg).

## Cloe and RAG Boundaries

Cloe is intended to help users understand decisions, experiments, and operational metrics. It should query only synthetic data, anonymized aggregates, internal policy documentation, model cards, system cards, and experiment summaries.

Cloe must not access CRM systems, raw identifiers, financial balances, income, precise location, or protected attributes. When explaining a decision, Cloe should use reason codes and policy metadata rather than personal or sensitive data.

## Guardrails

- No real personal data is used in the Datathon context.
- No credit, blocking, or eligibility decision is made exclusively by the model.
- Sensitive decisions require human review.
- Policy versions require offline validation before promotion.
- Secrets are handled through Key Vault and Managed Identity in the target Azure design.
- Logs must not contain direct identifiers or sensitive attributes.

## Expected Failure Modes

| Failure mode | Expected handling |
|--------------|-------------------|
| Invalid API payload | Reject with a structured validation error |
| No eligible offers | Return a no-decision response or configured fallback |
| Policy service unavailable | Use the deterministic baseline if approved for fallback |
| Reward arrives late | Store it as a delayed reward and evaluate separately |
| Drift alert triggered | Freeze promotion and require review |
| Cloe lacks evidence | Respond with uncertainty and point to available documentation |

## Monitoring

Technical monitoring should include latency, error rate, throughput, event write time, and service availability. Model monitoring should include conversion rate, cumulative regret, exploration ratio, reward latency, drift, and fairness index.

## Operational Boundaries

ECloe is not production-ready in the current repository state. A real deployment would require implementation, security review, legal review, data protection approval, incident response testing, and regulated financial suitability validation.

