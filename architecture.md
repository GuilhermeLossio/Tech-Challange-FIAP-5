# Target Azure Architecture - ECloe

This document describes the target Azure architecture for operating ECloe. The proposal prioritizes separation of responsibilities, auditability, secret management, observability, and a clear path from a demo environment to a production-ready setup.

## Overview

![Azure architecture flow](docs/azure-architecture-flow.svg)

The architecture is organized into channels, gateway, runtime services, data services, machine learning operations, security, and observability.

## Decision Flow

![Decision flow](docs/decision-flow.svg)

1. A digital channel sends minimized customer context to the Decision API.
2. The API validates the contract, authenticates the request, and calls the Bandit service.
3. The Bandit service selects the offer using the active policy.
4. The decision is recorded with `decision_id`, policy, version, offer, and reason codes.
5. Later events, such as click or conversion, update the reward tracker.
6. Offline pipelines recalculate metrics, drift, regret, and fairness.
7. A new policy is promoted only after validation and human approval.

## Azure Service Mapping

| Layer | Azure service | Role |  
|---|---|---|
| Gateway | Azure API Management | Authentication, rate limiting, CORS, and entry control |
| Runtime | Azure Kubernetes Service | Runs the Decision API, Bandit service, and LLM assistant |
| Training | Azure Machine Learning | Pipelines, experiments, MLflow tracking, and model registry |
| Events | Cosmos DB | Low-latency reads and writes for decisions and rewards |
| Artifacts | Blob Storage | Datasets, models, reports, and golden sets |
| RAG search | Azure AI Search | Index of synthetic policies, FAQs, governance documents, and model cards |
| Secrets | Key Vault | Keys, connection strings, and sensitive configuration |
| Identity | Managed Identity and Entra ID | Service access without hardcoded credentials |
| Observability | Application Insights and Log Analytics | Traces, technical metrics, and auditable logs |
| Alerts | Azure Monitor | Alerts for latency, errors, drift, conversion, and fairness |

## Minimum Contracts

### Decision Request

```json
{
  "customer_context": {
    "segment": "digital_high_engagement",
    "channel": "web",
    "risk_band": "low"
  },
  "eligible_offers": ["card_limit", "personal_loan", "cashback"],
  "request_id": "req_123"
}
```

### Decision Response

```json
{
  "decision_id": "dec_123",
  "offer_id": "cashback",
  "policy": "thompson_sampling",
  "policy_version": "2026-05-27.1",
  "reason_codes": ["segment_performance", "exploration_budget"]
}
```

### Reward Event

```json
{
  "decision_id": "dec_123",
  "event_type": "conversion",
  "reward": 1.0,
  "occurred_at": "2026-05-27T15:00:00Z"
}
```

## Security and Privacy

- Use Managed Identity for access between Azure workloads and services.
- Store secrets in Key Vault; do not store keys in versioned environment files.
- Minimize context attributes and avoid direct personal identifiers in the model.
- Record decision logs with pseudonymization and defined retention.
- Separate permissions for reading data, writing events, training models, and approving model releases.
- Apply rate limiting and authentication in API Management.

## Observability

Technical metrics:

- Decision API latency p50, p95, and p99.
- Error rate by endpoint.
- Throughput by channel.
- Event write time.
- Availability of data services.

Business and model metrics:

- Conversion rate by offer and segment.
- Cumulative regret.
- Exploration ratio.
- Reward latency.
- Context drift.
- Exposure variation across segments.

## Promotion and Rollback Strategy

![MLOps lifecycle](docs/mlops-lifecycle.svg)

1. Train or update a policy in an offline environment.
2. Evaluate it against the baseline and previous policy.
3. Validate minimum conversion, regret, and fairness metrics.
4. Register artifacts and metrics in Azure ML.
5. Submit the version for human approval.
6. Promote the approved version in the registry.
7. Release gradually in AKS.
8. Roll back to the previous version if degradation alerts are triggered.

## Qualitative Cost Estimate

| Component | Initial profile | Note |
|---|---|---|
| AKS | 2 to 4 small nodes | Adjust based on SLA and request volume |
| API Management | Developer for demo, Standard for production | Developer is not suitable for production SLA |
| Cosmos DB | Serverless at first | Move to provisioned throughput when volume is predictable |
| Azure ML | On-demand compute | Shut down clusters when they are not in use |
| Blob Storage | Hot or Cool tiers based on usage | Version datasets and artifacts |
| Application Insights | Pay-as-you-go | Control log volume and retention |
| Key Vault | Standard | Low cost and essential for security |

## Scale Scenarios

| Scenario | Suggested configuration |
|---|---|
| Demo | API Management Developer, small AKS cluster or container app, Cosmos DB serverless |
| 100 req/s | 2 Decision API pods, 1 to 2 Bandit service pods, HPA enabled |
| 1,000 req/s | API Management Standard, provisioned Cosmos DB, catalog cache, and aggressive HPA |
| Low night usage | Reduce replicas, shut down training compute, and review log retention |

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Policy favors a specific segment | Monitor exposure and fairness by segment |
| Delayed rewards distort learning | Separate immediate events from delayed rewards |
| Behavior drift | Use drift alerts and controlled retraining |
| Sensitive data leakage | Apply minimization, pseudonymization, and privacy review |
| Logging cost grows too much | Use sampling, appropriate retention, and focused dashboards |
