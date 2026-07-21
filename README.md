# ECloe - Datathon 7MLET
> **Low-cost next-best-action engine for integrated marketplace and digital wallet ecosystems.**

ECloe is a Machine Learning Engineering MVP that compares deterministic and adaptive decision policies for recommending the next best eligible action in a marketplace-finance journey. It simulates how marketplace behavior and digital wallet context can guide offers, messages, or benefits without making credit, fraud, or eligibility decisions. The active Etapa 1 data foundation is the public Kaggle Hillstrom email-campaign dataset, processed into minimized context, action, and reward columns for offline bandit evaluation.

---

## Capabilities

| Capability | Description |
|:---|:---|
| Offline experimentation | Uses Kaggle campaign rows as an offline simulation environment. |
| Marketplace-finance framing | Maps commerce behavior and wallet context to eligible financial actions. |
| Data minimization | Drops raw purchase amount and ZIP-level fields from the modeling dataset. |
| Adaptive recommendation | Compares Baseline, Epsilon-Greedy, UCB, and Thompson Sampling policies. |
| Local policy training | Runs deterministic offline policy simulation with local reports. |
| Evaluation-first delivery | Measures conversion rate, cumulative reward, regret, and exploration rate before selecting a policy. |
| Golden Set validation | Plans 5 deterministic examples for explainable Demo Day validation. |
| Low-consumption architecture | Prioritizes local execution and small Azure services instead of enterprise infrastructure. |

---

## Business Problem

Digital marketplaces connected to payment accounts need to decide which eligible financial action should be shown in moments such as home browsing, checkout, wallet engagement, or post-purchase follow-up. Static rules and long A/B tests can waste traffic, react slowly to behavior changes, and make responsible personalization harder to operate.

ECloe frames this as an adaptive experimentation problem: explore enough to learn, exploit the best known option when evidence is strong, and keep sensitive financial decisions outside the model. Upstream marketplace, wallet, compliance, and risk systems decide eligibility; ECloe only chooses which eligible action should be shown next.

Target product framing:

```text
Marketplace behavior + digital wallet context -> ECloe -> next best eligible action
```

See [`docs/marketplace-finance-use-case.md`](./docs/marketplace-finance-use-case.md) for the practical application scenario.

---

## Architecture

![Decision flow](docs/decision-flow.svg)

The MVP flow is intentionally simple: Kaggle data is downloaded and processed locally as a proxy for historical marketplace-finance interactions, offline policies are evaluated against the same simulated customer sequence, and the winning policy can later be exposed through a script, notebook, or lightweight demo interface. See [`Architecture.md`](./Architecture.md) for the full component breakdown, target Azure architecture, and pipeline flow.

Supporting diagrams:

- [`docs/decision-flow.svg`](./docs/decision-flow.svg) - decision and reward loop.
- [`docs/azure-architecture-flow.svg`](./docs/azure-architecture-flow.svg) - target Azure service map.
- [`docs/mlops-lifecycle.svg`](./docs/mlops-lifecycle.svg) - offline evaluation and promotion lifecycle.

---

## Dataset

The main dataset is Kaggle [`kevin-hillstrom-minethatdata-e-mailanalytics` by bofulee](https://www.kaggle.com/datasets/bofulee/kevin-hillstrom-minethatdata-e-mailanalytics).

Etapa 1 usage rules:

- `segment` is mapped to the decision action: `mens_email`, `womens_email`, or `no_email`.
- `conversion` is mapped to the binary reward used by the offline policies.
- `history_segment` is retained as a coarse context field.
- Raw monetary `history` and `zip_code` are excluded from the processed modeling dataset.
- Direct identifiers, income, wealth, gender, race, and private business rules are not used.

The default dataset is configured in [`.env.example`](.env.example):

```text
KAGGLE_DATASET=bofulee/kevin-hillstrom-minethatdata-e-mailanalytics
RAW_FILENAME=hillstrom.csv
PROCESSED_FILENAME=hillstrom_processed.csv
```

---

## Stage 3 Training Strategy

Bandit policies are not trained like a traditional classifier. ECloe uses the processed Hillstrom dataset as an offline simulation environment:

1. Each row represents a minimized campaign context.
2. The policy chooses one eligible action or simulated offer.
3. The simulator returns reward `1` for conversion or `0` otherwise.
4. The policy updates its statistics after each round.
5. All policies are compared on the same row order and reward assumptions.

Policy comparison:

| Policy | Role | Expected evidence |
|:---|:---|:---|
| Deterministic baseline | Control policy | Reference conversion and regret metrics. |
| Epsilon-Greedy | Simple adaptive policy | Exploration/exploitation trade-off with configurable `epsilon`. |
| UCB | Optimistic adaptive policy | Controlled exploration through an uncertainty bonus. |
| Thompson Sampling | Recommended main policy | Bayesian exploration with Beta priors for binary rewards. |

The algorithms are compared, not merged into one model. Thompson Sampling is the initial candidate for the final policy if offline results beat or technically tie the alternatives.

Run the local training workflow:

```bash
python -m src.evaluation.run
```

Prepare data and train in one command:

```bash
python -m src.evaluation.run --prepare-data
```

Run a smaller local experiment:

```bash
python -m src.evaluation.run --max-rows 5000
```

Expected training outputs:

```text
reports/policy_training/metrics.json
reports/policy_training/metrics.csv
reports/policy_training/policy_versions.json
reports/policy_training/selected_policy.json
reports/policy_training/golden_set_recommendations.json
reports/policy_training/policy_state_thompson_sampling.json
```

See [`docs/training-workflow.md`](./docs/training-workflow.md) for the full offline training flow.

---

## Project Structure

```text
.
├── data/
│   ├── raw/              # Original Kaggle files, ignored by git
│   ├── processed/        # Cleaned datasets, ignored by git
│   └── golden_set/       # Simplified evaluation cases
├── docs/                 # SVG diagrams and supporting documentation
├── notebooks/            # Reproducible notebooks for each essential stage
├── reports/              # Reports, metrics, and experiment outputs
├── src/
│   ├── bandits/          # Offline decision policies
│   ├── core/             # Settings and environment variable loading
│   ├── data/             # Kaggle download, schema, processing, and validation
│   ├── evaluation/       # Policy training and report generation
│   └── storage/          # Azure settings and expected document shapes
├── tests/                # Automated tests
├── Architecture.md       # Detailed architecture and pipeline documentation
├── pyproject.toml        # Dependencies and package configuration
├── .env.example          # Environment variable template
└── README.md             # Central project documentation
```

The current structure is consistent for a Python data/ML MVP. The policy training and notebook layers are now implemented; future work should add `src/demo/` when the recommendation interface is created.

---

## Getting Started

### Prerequisites

- Python 3.11 or newer.
- Kaggle account and API token.
- Local virtual environment recommended.

### Install

```bash
pip install -e ".[dev]"
```

Optional Azure dependencies:

```bash
pip install -e ".[azure]"
```

MLflow should be added when Stage 7 is implemented.

### Configure `.env`

```bash
cp .env.example .env
```

Required Kaggle variables:

```text
KAGGLE_USERNAME=
KAGGLE_KEY=
```

### Run Etapa 1

```bash
python -m src.data.download
python -m src.data.process
python -m src.data.validate
```

Expected local outputs:

```text
data/raw/hillstrom.csv
data/processed/hillstrom_processed.csv
reports/data_validation.json
```

The processor normalizes column names, validates the Hillstrom schema, removes duplicate rows, maps `segment -> action`, maps `conversion -> reward`, creates deterministic non-linkable `row_id` values, and writes a minimized modeling dataset.

### Run tests

```bash
python -m pytest
```

### Planned experiment commands

```bash
python -m src.evaluation.run
python -m src.demo.recommend --input data/golden_set/customer_001.json
mlflow ui
```

`python -m src.evaluation.run` is implemented for local reports. The demo command and MLflow UI remain planned future steps.

---

## Evaluation Metrics

| Metric | Purpose |
|:---|:---|
| Conversion rate | Measures positive rewards divided by total decisions. |
| Cumulative reward | Tracks total successful simulated outcomes. |
| Cumulative regret | Estimates the loss versus the best available alternative. |
| Exploration rate | Shows how often a policy selected uncertain alternatives. |
| Demo latency | Keeps the practical interface lightweight. |
| Operational consumption | Confirms the MVP avoids expensive infrastructure. |

---

## Golden Set

Stage 4 must include 5 examples with context, recommended action or offer, policy, and a short business justification. The Golden Set should be generated from the processed dataset or from documented synthetic examples.

| Case | Short context | Recommended offer | Policy |
|:---|:---|:---|:---|
| 1 | Digital customer with positive campaign evidence | `cashback_investment` | Thompson Sampling |
| 2 | Customer with credit-oriented context | `personal_loan` | Thompson Sampling |
| 3 | Segment with limited evidence | `credit_limit` | Thompson Sampling |
| 4 | Recurring digital-channel customer | `cashback_investment` | Thompson Sampling |
| 5 | Less-observed segment | `personal_loan` | Thompson Sampling |

---

## Deployment Strategy

The MVP should run locally first. A cloud demonstration should use a low-consumption Azure setup:

| Layer | Suggested service |
|:---|:---|
| Runtime | Azure App Service or Azure Container Apps |
| Artifacts | Azure Blob Storage |
| Events | Cosmos DB Serverless or small PostgreSQL |
| Secrets | Azure Key Vault |
| Observability | Application Insights |

AKS, Azure Machine Learning, API Management, and Azure AI Search remain future options, not MVP prerequisites.

The current Cosmos DB Serverless setup is documented in [`docs/cloud-setup.md`](./docs/cloud-setup.md).

---

## Related Docs

- [`Architecture.md`](./Architecture.md) - Architecture, components, pipeline, and trade-offs.
- [`docs/api-contract.md`](./docs/api-contract.md) - Planned Decision API and reward payloads.
- [`docs/marketplace-finance-use-case.md`](./docs/marketplace-finance-use-case.md) - Practical marketplace and digital wallet use case.
- [`docs/data-structure.md`](./docs/data-structure.md) - Local data folders and cloud storage conventions.
- [`docs/evaluation-plan.md`](./docs/evaluation-plan.md) - Offline evaluation and Golden Set expectations.
- [`docs/training-workflow.md`](./docs/training-workflow.md) - Implemented local policy training workflow.
- [`docs/cloud-setup.md`](./docs/cloud-setup.md) - Current low-consumption Azure Cosmos DB setup.
- [`docs/model-card.md`](./docs/model-card.md) - Policy intent, metrics, risks, and approval criteria.
- [`docs/system-card.md`](./docs/system-card.md) - System behavior, boundaries, and guardrails.
- [`docs/demo-script.md`](./docs/demo-script.md) - Demo Day presentation flow.
- [`docs/`](./docs) - SVG diagrams and supporting documentation.

---

## Limitations

- The Kaggle dataset is public and does not represent real customers from a financial institution.
- MVP offers and future reward assumptions are simulated to enable policy comparison.
- Offline rewards approximate a real environment but do not replace controlled production testing.
- Sensitive decisions would require human review, regulatory validation, security, privacy, and continuous monitoring.
- The cloud architecture is a target deployment, not a requirement for running the local MVP.

---

## License

MIT License. See [LICENSE](LICENSE).
