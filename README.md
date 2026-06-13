# ECloe - Datathon 7MLET

> Adaptive experimentation platform for personalized financial offers using multi-armed bandits, MLOps, governance, and an explainable LLM assistant named Cloe.

---

## Project Progress

| Stage | Description | Status |
|-------|-------------|--------|
| 0 | Project organization | In progress |
| 1 | Kaggle dataset and EDA | Pending |
| 2 | Synthetic enrichment | Pending |
| 3 | Baseline and algorithmic strategy | Pending |
| 4 | Offline evaluation and golden set | Pending |
| 5 | Demonstrable service or interface | Pending |
| 6 | MVP and target Azure architecture | Drafted in `architecture.md` |
| 7 | MLOps lifecycle | Pending |
| 8 | Governance, Demo Day, and reports | Pending |

---

## Problem Overview

Digital financial institutions often rely on static rules or long A/B tests to decide which offer should be shown to each customer. This wastes traffic, slows learning, and makes responsible personalization harder to operate.

**ECloe** proposes a decision engine that learns from each interaction, with Cloe acting as an LLM assistant that explains and summarizes experiments:

![Decision flow](docs/decision-flow.svg)

The project does not simulate a real bank. Its goal is to demonstrate **ML Engineering maturity**: framing the problem, building baselines, versioning data, serving decisions, evaluating quality, and governing the lifecycle with support from an explainable LLM assistant.

---

## Design Choices

### Reference Dataset

The project uses the Kaggle [`bank-marketing` dataset by henriqueyamahata](https://www.kaggle.com/datasets/henriqueyamahata/bank-marketing) as its factual foundation because it is aligned with banking campaigns and conversion propensity. The `duration` column is excluded because it causes temporal leakage, as it is only known after contact.

### Algorithms

| Policy | Role | Rationale |
|--------|------|-----------|
| Thompson Sampling | Main policy | Bayesian exploration with explicit uncertainty, suitable for binary rewards |
| Nilos-UCB | Technical comparison | UCB-family policy with documented formula and trade-off analysis |
| Deterministic baseline | Control | Historical best arm used as a reference for measuring gain and regret |

### Synthetic Data and LGPD

**No real personal data is used.** The system operates entirely on synthetic data derived from the Kaggle dataset, following the challenge constraint.

In a future production scenario, the platform would require a documented privacy plan covering legal basis, data minimization, retention, and incident response. In this repository context, the LLM assistant only queries synthetic data and synthetic internal policies through RAG; no real identifier is indexed.

The hypothetical production privacy approach is documented in [`docs/lgpd-plan.md`](docs/lgpd-plan.md).

---

## Repository Structure

```text
.
+-- docs/
|   +-- api-contract.md
|   +-- azure-architecture-flow.svg
|   +-- data-generation.md
|   +-- demo-script.md
|   +-- decision-flow.svg
|   +-- evaluation-plan.md
|   +-- glossary.md
|   +-- governance.md
|   +-- lgpd-plan.md
|   +-- model-card.md
|   +-- mlops-lifecycle.svg
|   +-- system-card.md
+-- architecture.md
+-- README.md
+-- .gitignore
+-- LICENSE
```

The structure above reflects the current documentation-focused state of the repository. The planned MVP implementation structure is:

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

---

## Documentation Index

| Document | Purpose |
|----------|---------|
| [`architecture.md`](architecture.md) | MVP-first Azure architecture, target enterprise architecture, and deployment considerations |
| [`docs/api-contract.md`](docs/api-contract.md) | Planned Decision API and reward event payloads |
| [`docs/data-generation.md`](docs/data-generation.md) | Synthetic data generation approach and validation checks |
| [`docs/evaluation-plan.md`](docs/evaluation-plan.md) | Offline evaluation, golden set, metrics, and approval criteria |
| [`docs/governance.md`](docs/governance.md) | Release approval, rollback, audit, ownership, and compliance checkpoints |
| [`docs/lgpd-plan.md`](docs/lgpd-plan.md) | Hypothetical production privacy and LGPD plan |
| [`docs/model-card.md`](docs/model-card.md) | Policy intent, metrics, risks, fairness, and approval criteria |
| [`docs/system-card.md`](docs/system-card.md) | System behavior, Cloe/RAG boundaries, guardrails, and monitoring |
| [`docs/demo-script.md`](docs/demo-script.md) | Suggested Demo Day presentation flow |
| [`docs/glossary.md`](docs/glossary.md) | Definitions of project terms |

---

## Local Execution

The implementation is not available yet. When the codebase is added, the expected local workflow is:

```bash
# 1. Clone the repository
git clone https://github.com/<org>/datathon-7mlet-ecloe-grupo-XX.git
cd datathon-7mlet-ecloe-grupo-XX

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Configure environment variables
cp .env.example .env

# 4. Download and prepare Kaggle data
python -m src.data.download
python -m src.data.process

# 5. Generate synthetic enrichment
python -m src.data.synthetic --seed 42

# 6. Run offline evaluation
python -m src.evaluation.run --golden-set data/golden_set/evaluation_cases.jsonl

# 7. Start the local Decision API
uvicorn src.api.main:app --reload
```

---

## Components

| Component | Responsibility |
|-----------|----------------|
| Decision API | Receives context, validates the contract, and returns a recommended offer with reason codes |
| Bandit service | Runs Thompson Sampling, Nilos-UCB, and the control baseline |
| Reward tracker | Records clicks, conversions, and delayed rewards |
| MLOps pipeline | Trains, evaluates, versions, and approves new policies |
| Cloe LLM assistant | Explains decisions and summarizes experiments through RAG over synthetic data |
| Observability | Monitors latency, drift, regret, conversion, and fairness |

---

## Evaluation Metrics

| Metric | Description |
|--------|-------------|
| Conversion rate | Conversion by offer, segment, and period |
| Cumulative regret | Accumulated gap between the selected policy and the estimated optimal policy |
| Exploration ratio | Share of exploratory decisions |
| Reward latency | Average time until reward observation |
| Fairness index | Relative exposure across synthetic segments |
| API latency p95 | Decision engine response time at the 95th percentile |

---

## Azure Architecture

The Azure plan is documented in [`architecture.md`](architecture.md) as a phased strategy. ECloe keeps a target enterprise architecture, but the first implementation should be a smaller MVP to reduce cost, complexity, and delivery risk.

![Azure architecture flow](docs/azure-architecture-flow.svg)

The first infrastructure version should prioritize:

- FastAPI Decision API.
- Thompson Sampling policy.
- Deterministic baseline.
- Reward tracking.
- Azure Blob Storage for datasets, golden sets, model artifacts, and reports.
- Cosmos DB Serverless for decision events, reward events, and policy versions.
- Key Vault and Managed Identity when possible.
- Basic observability with Application Insights.
- Synthetic-only data.

Recommended MVP deployment:

- Frontend/demo: Vercel, Streamlit, Hugging Face Space, or a simple local dashboard.
- Runtime: Azure Container Apps or Azure App Service. Avoid AKS in the first version.
- Data: Blob Storage and Cosmos DB Serverless.
- Security: Key Vault, Managed Identity when possible, no hardcoded credentials, and no real personal data.
- Observability: API latency, error rate, decision count, reward count, and policy version tracking.

The target enterprise architecture remains relevant for later phases. It covers:

- Azure API Management as the entry gateway.
- AKS for the Decision API, bandit service, and LLM assistant.
- Azure Machine Learning for tracking, pipelines, and model registry.
- Cosmos DB for offer and reward events.
- Blob Storage for datasets and artifacts.
- Azure AI Search for the RAG index over synthetic data.
- Key Vault and Managed Identity for secrets and credentials.
- Application Insights and Log Analytics for observability.

---

## MLOps Lifecycle

![MLOps lifecycle](docs/mlops-lifecycle.svg)

The lifecycle separates offline experimentation from serving. Policies are promoted only after metric validation, human approval, and registry versioning.

---

## Governance

- Auditable logs for each decision, including minimized context, offer, policy, and version.
- Reason codes for each recommendation.
- Separation between identity systems and behavioral model features.
- Human approval before promoting policies to production.
- Documented rollback for degraded policies.
- Monitoring for drift, latency, errors, and fairness.
- Secrets managed through Key Vault and Managed Identity.
- Privacy controls and LGPD assumptions documented in [`docs/lgpd-plan.md`](docs/lgpd-plan.md).

---

## Known Limitations

- The repository is in a documentation and planning phase; most implementation components are not present yet.
- Data is synthetic or derived from a public Kaggle dataset and does not represent real customer behavior.
- Azure cost estimates are qualitative and must be recalculated based on region, volume, and final SLA.
- The solution must not be used in regulated production without full risk, suitability, security, and privacy validation.

---

## License

MIT License. See [LICENSE](LICENSE).
