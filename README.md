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
| 6 | Target Azure architecture | Drafted in `architecture.md` |
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

---

## Repository Structure

```text
.
+-- docs/
|   +-- azure-architecture-flow.svg
|   +-- decision-flow.svg
|   +-- mlops-lifecycle.svg
+-- architecture.md
+-- README.md
+-- .gitignore
+-- LICENSE
```

The structure above reflects the current documentation-focused state of the repository. Planned implementation folders for data, notebooks, reports, source code, and tests are described as target components rather than existing assets.

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

The target Azure architecture is detailed in [`architecture.md`](architecture.md).

![Azure architecture flow](docs/azure-architecture-flow.svg)

It covers:

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

---

## Known Limitations

- The repository is in a documentation and planning phase; most implementation components are not present yet.
- Data is synthetic or derived from a public Kaggle dataset and does not represent real customer behavior.
- Azure cost estimates are qualitative and must be recalculated based on region, volume, and final SLA.
- The solution must not be used in regulated production without full risk, suitability, security, and privacy validation.

---

## License

MIT License. See [LICENSE](LICENSE).
