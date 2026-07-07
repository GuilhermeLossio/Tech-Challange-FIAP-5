# 🚀 ECloe - Datathon 7MLET
> **Low-cost adaptive experimentation platform for financial next-best-action recommendations.**

ECloe is a Machine Learning Engineering MVP that compares deterministic and adaptive decision policies for recommending financial offers, messages, or next-best actions in digital channels. The project uses the public Kaggle Bank Marketing dataset as a factual base, simulates offer rewards offline, tracks experiments locally, and keeps the first deployable architecture intentionally small.

---

## 🚀 Capabilities

| Capability | Description |
|:---|:---|
| 🧪 **Offline experimentation** | Uses Kaggle customer/campaign rows as an offline simulation environment. |
| 🎯 **Adaptive recommendation** | Compares Baseline, Epsilon-Greedy, UCB, and Thompson Sampling policies. |
| 📊 **Evaluation-first delivery** | Measures conversion rate, cumulative reward, regret, and exploration rate before selecting a policy. |
| 🧾 **Golden Set validation** | Plans 5 deterministic customer examples for explainable Demo Day validation. |
| ⚙️ **Local MLOps** | Uses local MLflow tracking for parameters, metrics, and evaluation artifacts. |
| 💸 **Low-consumption architecture** | Prioritizes local execution and small Azure services instead of enterprise infrastructure. |

---

## 🧩 Business Problem

Digital financial institutions need to decide which offer, message, or next-best action should be shown to each eligible customer. Static rules and long A/B tests can waste traffic, react slowly to behavior changes, and make responsible personalization harder to operate.

ECloe frames this as an adaptive experimentation problem: explore enough to learn, exploit the best known option when evidence is strong, and keep sensitive financial decisions under human governance.

---

## 🏗️ Architecture

![Decision flow](docs/decision-flow.svg)

The MVP flow is intentionally simple: Kaggle data is downloaded and processed locally, offline policies are evaluated against the same simulated customer sequence, and the winning policy can later be exposed through a script, notebook, or lightweight API. See [`Architecture.md`](./Architecture.md) for the full component breakdown, target Azure architecture, and pipeline flow.

Supporting diagrams:

- [`docs/decision-flow.svg`](./docs/decision-flow.svg) — decision and reward loop.
- [`docs/azure-architecture-flow.svg`](./docs/azure-architecture-flow.svg) — target Azure service map.
- [`docs/mlops-lifecycle.svg`](./docs/mlops-lifecycle.svg) — offline evaluation and promotion lifecycle.

---

## 📦 Dataset

The main dataset is Kaggle [`bank-marketing` by henriqueyamahata](https://www.kaggle.com/datasets/henriqueyamahata/bank-marketing).

Usage rules:

- `y` is the observed conversion signal.
- `duration` is removed because it is only known after contact and causes temporal leakage.
- Real customer identifiers, income, wealth, gender, race, and private business rules are not used.
- Any synthetic offer or reward layer must be documented and reproducible.

The default dataset is configured in [`.env.example`](.env.example):

```text
KAGGLE_DATASET=henriqueyamahata/bank-marketing
```

---

## 🧠 Stage 3 Training Strategy

Bandit policies are not trained like a traditional classifier. ECloe uses the Kaggle dataset as an offline simulation environment:

1. Each row represents a customer/context.
2. The policy chooses one simulated offer.
3. The simulator returns reward `1` for success or `0` for failure.
4. The policy updates its statistics after each round.
5. All policies are compared on the same customer order and reward assumptions.

Simulated MVP offers:

| Offer ID | Description |
|:---|:---|
| `credit_limit` | Credit limit increase or pre-approved credit |
| `personal_loan` | Personal loan offer |
| `cashback_investment` | Cashback or investment incentive |

Policy comparison:

| Policy | Role | Expected evidence |
|:---|:---|:---|
| Deterministic baseline | Control policy | Reference conversion and regret metrics. |
| Epsilon-Greedy | Simple adaptive policy | Exploration/exploitation trade-off with configurable `epsilon`. |
| UCB | Optimistic adaptive policy | Controlled exploration through an uncertainty bonus. |
| Thompson Sampling | Recommended main policy | Bayesian exploration with Beta priors for binary rewards. |

The algorithms are compared, not merged into one model. Thompson Sampling is the initial candidate for the final policy if offline results beat or technically tie the alternatives.

---

## 🗂️ Project Structure

```text
.
├── data/
│   ├── raw/              # Original Kaggle files, ignored by git
│   ├── processed/        # Cleaned datasets, ignored by git
│   └── golden_set/       # Simplified evaluation cases
├── docs/                 # SVG diagrams and supporting documentation
├── reports/              # Reports, metrics, and experiment outputs
├── src/
│   ├── core/             # Settings and environment variable loading
│   ├── data/             # Kaggle download and dataset processing
│   └── storage/          # Azure settings and expected document shapes
├── tests/                # Automated tests
├── Architecture.md       # Detailed architecture and pipeline documentation
├── pyproject.toml        # Dependencies and package configuration
├── .env.example          # Environment variable template
└── README.md             # Central project documentation
```

The current structure is consistent for a Python data/ML MVP. Future implementation work should add `src/bandits/`, `src/evaluation/`, `src/demo/`, and `notebooks/` when those components are created.

---

## ⚙️ Getting Started

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

### Download and process data

```bash
python -m src.data.download
python -m src.data.process
```

The current processor normalizes column names, removes `duration`, maps `y` to `1`/`0`, and removes duplicates.

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

---

## 📈 Evaluation Metrics

| Metric | Purpose |
|:---|:---|
| Conversion rate | Measures positive rewards divided by total decisions. |
| Cumulative reward | Tracks total successful simulated outcomes. |
| Cumulative regret | Estimates the loss versus the best available alternative. |
| Exploration rate | Shows how often a policy selected uncertain alternatives. |
| Demo latency | Keeps the practical interface lightweight. |
| Operational consumption | Confirms the MVP avoids expensive infrastructure. |

---

## 🧾 Golden Set

Stage 4 must include 5 customer examples with context, recommended offer, policy, and a short business justification. The Golden Set should be generated from the processed dataset or from documented synthetic examples.

| Case | Short context | Recommended offer | Policy |
|:---|:---|:---|:---|
| 1 | Digital customer with positive campaign evidence | `cashback_investment` | Thompson Sampling |
| 2 | Customer with credit-oriented context | `personal_loan` | Thompson Sampling |
| 3 | Segment with limited evidence | `credit_limit` | Thompson Sampling |
| 4 | Recurring digital-channel customer | `cashback_investment` | Thompson Sampling |
| 5 | Less-observed segment | `personal_loan` | Thompson Sampling |

---

## 🚢 Deployment Strategy

The MVP should run locally first. A cloud demonstration should use a low-consumption Azure setup:

| Layer | Suggested service |
|:---|:---|
| Runtime | Azure App Service or Azure Container Apps |
| Artifacts | Azure Blob Storage |
| Events | Cosmos DB Serverless or small PostgreSQL |
| Secrets | Azure Key Vault |
| Observability | Application Insights |

AKS, Azure Machine Learning, API Management, and Azure AI Search remain future options, not MVP prerequisites.

---

## 📋 Related Docs

- [`Architecture.md`](./Architecture.md) — Architecture, components, pipeline, and trade-offs.
- [`docs/api-contract.md`](./docs/api-contract.md) — Planned Decision API and reward payloads.
- [`docs/data-structure.md`](./docs/data-structure.md) — Local data folders and cloud storage conventions.
- [`docs/evaluation-plan.md`](./docs/evaluation-plan.md) — Offline evaluation and Golden Set expectations.
- [`docs/model-card.md`](./docs/model-card.md) — Policy intent, metrics, risks, and approval criteria.
- [`docs/system-card.md`](./docs/system-card.md) — System behavior, boundaries, and guardrails.
- [`docs/demo-script.md`](./docs/demo-script.md) — Demo Day presentation flow.
- [`docs/`](./docs) — SVG diagrams and supporting documentation.

---

## ⚠️ Limitations

- The Kaggle dataset is public and does not represent real customers from a financial institution.
- MVP offers are simulated to enable policy comparison.
- Offline rewards approximate a real environment but do not replace controlled production testing.
- Sensitive decisions would require human review, regulatory validation, security, privacy, and continuous monitoring.
- The cloud architecture is a target deployment, not a requirement for running the local MVP.

---

## 📜 License

MIT License. See [LICENSE](LICENSE).
