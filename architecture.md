# Azure Architecture - ECloe

This document describes a pragmatic MVP-first Azure architecture for ECloe and the target enterprise architecture for later phases. The project should keep the enterprise target, but the first implementation must start smaller to reduce cost, complexity, and delivery risk.

## Overview

![Azure architecture flow](docs/azure-architecture-flow.svg)

The target architecture is organized into channels, gateway, runtime services, data services, machine learning operations, security, and observability. For the MVP, the same responsibilities exist, but the platform uses fewer managed services and avoids Kubernetes until the operating need is clear.

## Phase 1: MVP Cloud Architecture

The first infrastructure version should prove the decisioning loop before introducing enterprise platform overhead.

### Scope

- FastAPI Decision API.
- Thompson Sampling policy.
- Deterministic baseline for control and fallback.
- Reward tracking linked by `decision_id`.
- Synthetic-only data.
- Azure Blob Storage for datasets, golden sets, model artifacts, and reports.
- Cosmos DB Serverless for decision events, reward events, and policy versions.
- Azure Key Vault for secrets.
- Managed Identity where supported by the runtime.
- Basic observability through Application Insights.

### Recommended Service Mapping

| Layer | Recommended MVP option | Role |
|---|---|---|
| Frontend/demo | Vercel, Streamlit, Hugging Face Space, or local dashboard | Demonstrates decisions, rewards, and metrics |
| Runtime | Azure Container Apps or Azure App Service | Runs the FastAPI Decision API and bandit policy |
| Events | Cosmos DB Serverless | Stores decision events, reward events, and policy versions |
| Artifacts | Azure Blob Storage | Stores datasets, golden sets, model artifacts, and reports |
| Secrets | Azure Key Vault | Stores connection strings, API keys, and runtime secrets |
| Identity | Managed Identity where possible | Avoids hardcoded credentials for Azure service access |
| Observability | Application Insights | Tracks API latency, errors, decision count, reward count, and policy versions |

AKS, API Management, Azure ML, Azure AI Search, full observability, and advanced governance should not block the MVP. They remain part of the target enterprise architecture and can be introduced when request volume, security posture, model lifecycle needs, or stakeholder requirements justify them.

### MVP Security Rules

- No hardcoded credentials.
- No real personal data.
- Use Key Vault for secrets.
- Use Managed Identity when supported by the selected runtime.
- Keep all datasets synthetic or public-source-derived and free of direct identifiers.

### MVP Observability

The first dashboard should focus on operational and policy health:

- API latency.
- Error rate.
- Decision count.
- Reward count.
- Active policy and policy version.
- Cosmos DB write failures.
- Blob artifact read/write failures.

## Target Enterprise Architecture

The enterprise target adds gateway controls, Kubernetes orchestration, managed ML lifecycle, RAG search, richer monitoring, and mature governance. It is the desired end state, not the required first deployment.

## Decision Flow

![Decision flow](docs/decision-flow.svg)

1. A digital channel sends minimized customer context to the Decision API.
2. The API validates the contract, authenticates the request, and calls the Bandit service.
3. The Bandit service selects the offer using the active policy.
4. The decision is recorded with `decision_id`, policy, version, offer, and reason codes.
5. Later events, such as click or conversion, update the reward tracker.
6. Offline pipelines recalculate metrics, drift, regret, and fairness.
7. A new policy is promoted only after validation and human approval.

## Target Azure Service Mapping

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

## Planned Repository Structure

```text
src/
  api/
    main.py
    schemas.py
  bandits/
    thompson.py
    nilos_ucb.py
    baseline.py
  data/
    download.py
    process.py
    synthetic.py
  evaluation/
    run.py
    metrics.py
  storage/
    cosmos.py
    blob.py
tests/
  test_bandits.py
  test_api_contract.py
  test_metrics.py
infra/
  azure/
    main.bicep
    parameters.dev.json
.env.example
pyproject.toml
Dockerfile
```

## Minimum Contracts

The detailed API and reward payload definitions are maintained in [`docs/api-contract.md`](docs/api-contract.md). The examples below summarize the main integration shape.

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
- Do not use hardcoded credentials in code, notebooks, infrastructure files, or demos.
- Use only synthetic data in the repository and MVP environment.
- Minimize context attributes and avoid direct personal identifiers in the model.
- Record decision logs with pseudonymization and defined retention.
- Separate permissions for reading data, writing events, training models, and approving model releases.
- Apply rate limiting and authentication in API Management.
- Keep the production privacy assumptions aligned with [`docs/lgpd-plan.md`](docs/lgpd-plan.md).

## Observability

The metric definitions and approval gates are detailed in [`docs/evaluation-plan.md`](docs/evaluation-plan.md).

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

Release ownership, approval, and rollback controls are detailed in [`docs/governance.md`](docs/governance.md).

1. Train or update a policy in an offline environment.
2. Evaluate it against the baseline and previous policy.
3. Validate minimum conversion, regret, and fairness metrics.
4. Register artifacts and metrics in Blob Storage for the MVP, then Azure ML in the target enterprise phase.
5. Submit the version for human approval.
6. Promote the approved version in the policy version store.
7. Release through App Service or Container Apps in the MVP, then gradually in AKS in the target enterprise phase.
8. Roll back to the previous version if degradation alerts are triggered.

## Qualitative Cost Estimate

| Component | Initial profile | Note |
|---|---|---|
| Azure Container Apps or App Service | Small instance or consumption-oriented profile | Preferred MVP runtime for the FastAPI service |
| Cosmos DB | Serverless | Good fit for low and irregular MVP event volume |
| Blob Storage | Hot or Cool tiers based on usage | Version datasets and artifacts |
| Application Insights | Pay-as-you-go | Control log volume and retention |
| Key Vault | Standard | Low cost and essential for security |
| AKS | Later enterprise phase | Add only when orchestration needs justify the cost and operational complexity |
| API Management | Later enterprise phase | Add for mature gateway, quota, and external API management needs |
| Azure ML | Later enterprise phase | Add for managed pipelines, registry, and experiment tracking |
| Azure AI Search | Later enterprise phase | Add when Cloe's RAG index is implemented beyond local or static documents |

## Scale Scenarios

| Scenario | Suggested configuration |
|---|---|
| MVP demo | Local dashboard, Streamlit, Vercel, or Hugging Face Space with FastAPI on Container Apps or App Service |
| MVP cloud | Container Apps or App Service, Cosmos DB Serverless, Blob Storage, Key Vault, Application Insights |
| Enterprise demo | API Management Developer, small AKS cluster or container app, Cosmos DB serverless |
| 100 req/s | 2 Decision API pods or app replicas, 1 to 2 Bandit service replicas, autoscaling enabled |
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
