# Architecture - ECloe

ECloe is a low-cost adaptive experimentation MVP for financial next-best-action recommendations. It currently contains Hillstrom data ingestion/processing code, validation reports, storage configuration shapes, tests, and documentation for planned offline policy evaluation and a demo interface.

## Overview

![Decision flow](docs/decision-flow.svg)

The system starts with the public Kaggle Hillstrom email-campaign dataset, processes it into a minimized local dataset, evaluates multiple recommendation policies offline, and prepares the selected policy for a small demonstrable interface. The decision flow above shows the intended runtime loop: a channel sends minimized context and eligible offers, the policy selects one action, the decision is logged, and later rewards are linked back to the original `decision_id`.

## Components

| Component | Responsibility | Key files/paths |
|:---|:---|:---|
| Configuration | Loads local `.env` settings, data paths, Kaggle dataset slug, file names, seed, and Azure placeholders. | `src/core/config.py`, `.env.example` |
| Data ingestion | Downloads the configured Hillstrom Kaggle dataset into `data/raw/hillstrom.csv`. | `src/data/download.py` |
| Data schema | Defines accepted source columns, minimized context columns, allowed actions, rewards, and blocked columns. | `src/data/schemas.py` |
| Data processing | Normalizes columns, validates required fields, maps `segment -> action`, maps `conversion -> reward`, removes blocked modeling fields, and writes processed CSV output. | `src/data/process.py`, `tests/test_data_process.py` |
| Data validation | Produces `reports/data_validation.json` with missing values, duplicate count, action distribution, conversion rate, blocked columns, and validity status. | `src/data/validate.py`, `tests/test_data_validate.py` |
| Storage contracts | Defines target Azure settings and Cosmos DB document shapes for future decision/reward storage. | `src/storage/` |
| Offline policy layer | Implements Baseline, Epsilon-Greedy, UCB, and Thompson Sampling evaluation. | `src/bandits/`, `src/evaluation/` |
| Notebooks | Reproduce the essential data, validation, training, evaluation, and cloud-reference stages. | `notebooks/` |
| Demo interface | Planned script, notebook, or simple API that returns a recommended offer for a customer context. | Planned `src/demo/` or `src/api/` |
| Documentation | Central delivery documentation, diagrams, contracts, governance, model card, and demo script. | `README.md`, `docs/` |

## Data / ML Pipeline Flow

![MLOps lifecycle](docs/mlops-lifecycle.svg)

The MVP pipeline is intentionally small:

1. Download the Kaggle Hillstrom email-campaign dataset.
2. Process the dataset into minimized context, action, and reward columns.
3. Validate that no blocked columns are present in the processed dataset.
4. Simulate offer choices and binary rewards for offline policy comparison.
5. Run the deterministic baseline and adaptive policies on the same offline sequence.
6. Write local policy metrics and artifacts under `reports/policy_training/`.
7. Select the policy for the Golden Set and demo interface.

## Target Azure Architecture

![Azure architecture flow](docs/azure-architecture-flow.svg)

The target cloud architecture keeps the MVP low-consumption:

| Layer | MVP option | Role |
|:---|:---|:---|
| Runtime | Azure App Service or Azure Container Apps | Runs a future script-backed API or lightweight FastAPI service. |
| Artifacts | Azure Blob Storage | Stores processed datasets, Golden Set files, metrics, and policy artifacts. |
| Events | Cosmos DB Serverless or small PostgreSQL | Stores decision events, reward events, and policy versions. |
| Secrets | Azure Key Vault | Keeps Kaggle, storage, and runtime credentials outside code. |
| Observability | Application Insights | Tracks latency, error rate, decision count, and reward count. |

AKS, Azure Machine Learning, API Management, and Azure AI Search are future enterprise options. They should not block the Datathon MVP.

The current Cosmos DB Serverless setup is documented in [`docs/cloud-setup.md`](docs/cloud-setup.md).

## API and Event Contracts

The planned Decision API and reward payloads are documented in [`docs/api-contract.md`](docs/api-contract.md). The MVP now includes a local policy training script documented in [`docs/training-workflow.md`](docs/training-workflow.md), and can later expose the same request/response shape through FastAPI if needed for Demo Day.

## Key Design Decisions

- **Local-first execution** - keeps the project easy to run and avoids unnecessary cloud cost during the Datathon.
- **Public Kaggle data only** - avoids real customer data and makes the experiment reproducible.
- **Minimized Hillstrom context** - keeps `history_segment` but drops raw monetary `history` and `zip_code` from the modeling dataset.
- **Explicit action/reward mapping** - uses `segment` as the observed campaign action and `conversion` as the binary reward.
- **Compare policies instead of merging them** - Baseline, Epsilon-Greedy, UCB, and Thompson Sampling are evaluated as separate strategies.
- **Use Thompson Sampling as the initial candidate** - it fits binary rewards and handles uncertainty with documented Beta priors.
- **Keep cloud as a target architecture** - small Azure services are enough for a demo; enterprise services remain future work.

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

## Limitations

- The repository does not yet include MLflow runs or a demo interface.
- The target Azure services are architectural guidance, not deployed infrastructure.
- Offline simulation is useful for engineering validation, but it is not production evidence.
- A regulated production deployment would require legal, security, privacy, model risk, and operational reviews.
