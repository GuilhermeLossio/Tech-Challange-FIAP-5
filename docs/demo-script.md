# Demo Script - ECloe

## Goal

Use this script to present ECloe as an ML Engineering project for adaptive financial offer experimentation. The demo should be clear that the repository is documentation-first and uses synthetic or public-source-derived data only.

## Suggested Flow

### 1. Problem

Digital financial channels often choose offers using static rules or long A/B tests. ECloe proposes adaptive experimentation so the system can learn from each interaction while preserving governance and auditability.

### 2. Solution Overview

Show the decision flow in [`decision-flow.svg`](decision-flow.svg). Explain that the channel sends minimized context, the Decision API calls the active bandit policy, the offer is returned with reason codes, and later reward events improve future policy versions.

### 3. Architecture

Show [`azure-architecture-flow.svg`](azure-architecture-flow.svg), but explicitly separate the MVP from the target enterprise architecture.

For the MVP, explain that ECloe should start with a FastAPI Decision API running on Azure Container Apps or Azure App Service, backed by Blob Storage, Cosmos DB Serverless, Key Vault, Managed Identity where possible, and basic Application Insights telemetry. The MVP should avoid AKS, API Management, Azure ML, and Azure AI Search until the core decision, reward, and evaluation loop is proven.

For the target architecture, highlight API Management, AKS runtime services, Cosmos DB, Blob Storage, Azure ML, Azure AI Search, Key Vault, full observability, and advanced governance.

### 4. Decision Example

Use the example request from [`api-contract.md`](api-contract.md):

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

Then show the expected response with `decision_id`, `offer_id`, `policy`, `policy_version`, and `reason_codes`.

### 5. Cloe Explanation

Explain that Cloe uses RAG over synthetic data, policy documentation, model cards, system cards, and experiment summaries. Cloe does not access CRM systems, direct identifiers, or sensitive attributes.

### 6. Evaluation

Use [`evaluation-plan.md`](evaluation-plan.md) to describe conversion rate, cumulative regret, exploration ratio, reward latency, fairness index, and API latency p95.

### 7. Governance and LGPD

Summarize that no real personal data is used in the Datathon context. For a hypothetical production scenario, governance and privacy controls are documented in [`governance.md`](governance.md) and [`lgpd-plan.md`](lgpd-plan.md).

### 8. Limitations

Close with the main limitations:

- The repository is currently documentation-first.
- The first implementation should be a pragmatic MVP, not the full enterprise Azure architecture.
- Results would be synthetic and not production evidence.
- Production deployment would require implementation, legal review, security review, and regulated financial validation.

## Suggested Closing

ECloe demonstrates how adaptive ML decisioning can be designed with evaluation, observability, privacy, explainability, and governance from the start.
