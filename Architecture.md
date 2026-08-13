# Architecture - ECloe

ECloe is a low-cost adaptive experimentation MVP for next-best-action recommendations in an integrated marketplace and digital wallet ecosystem. The product story is composed of ECloe Market, ECloe Pay, and ECloe Engine. It currently contains Hillstrom data ingestion/processing code, offline policy evaluation, a lightweight purchase-likelihood validator, a local FastAPI service, validation reports, storage configuration shapes, tests, notebooks, and documentation for a future demo interface.

Author: Guilherme Lossio, Senior ML Engineer. Academic context: project for the fifth step of the FIAP MBA in Machine Learning.

## Overview

![Decision flow](docs/decision-flow.svg)

The system starts with the public Kaggle Hillstrom email-campaign dataset, processes it into a minimized local dataset, evaluates multiple recommendation policies offline, and prepares the selected policy for a small demonstrable interface. Hillstrom is used as a public proxy for the pattern ECloe needs: context, action, and reward. In the target product, ECloe Market produces commerce behavior signals, ECloe Pay provides wallet context and eligible actions, ECloe Engine selects one next best action, the decision is logged, and later rewards are linked back to the original `decision_id`.

## Demo Interface Layer

![Demo interface flow](docs/demo-interface-flow.svg)

The implemented Flask demo exposes ECloe Market and ECloe Pay as one simulated application. It builds minimized context and eligible candidates before invoking the shared recommendation service. ECloe Engine remains an independent FastAPI boundary for external channels.

| Layer | Status | Responsibility |
|:---|:---|:---|
| Demo frontend | Implemented | Presents the launcher, marketplace, cart, recommendation shelf, wallet, and technical state. |
| Demo Backend-for-Frontend | Implemented | Holds demo session state, builds minimized context, supplies eligible candidates, and orchestrates domain APIs. |
| Context aggregation | Implemented | Converts domain state into allowlisted coarse bands and neutral categories. |
| Eligibility simulation | Planned for demo | Produces eligible offers before the decision request. ECloe Engine must not invent eligibility. |
| ECloe Engine | Implemented | Serves health, policy metadata, likelihood estimates, decisions, and reward ingestion through `src/api/`. |
| Decision and reward persistence | Implemented | Persists decisions and reward events through the configured repository mode. |
| ECloe Control Room | Planned for demo | Explains request/response payloads, policies, artifacts, event timelines, and operational status for evaluators. |

Current implemented architecture is the local ECloe Engine API, offline evaluation pipeline, purchase-likelihood artifact, and persistence layer. Planned demo architecture adds the simulated UI and BFF around that API. Future production integration would replace the simulated eligibility and session layers with governed upstream marketplace, wallet, risk, compliance, and operations systems.

The planned interface is detailed in [`docs/demo-interface.md`](docs/demo-interface.md), with the marketplace-specific ECloe Market scope separated in [`docs/ecloe-market.md`](docs/ecloe-market.md) and the wallet-specific ECloe Pay scope separated in [`docs/ecloe-pay.md`](docs/ecloe-pay.md). These documents explicitly separate the current online serving strategy from the offline promoted policy and future adaptive strategies.

## Recommendation System

![Recommendation system overview](docs/recommendation-system-overview.svg)

Market and Pay have independent policies and objectives behind one typed Engine API. The serving default is the deterministic baseline. The likelihood ranker is guarded by minimum evidence, while Epsilon-Greedy, UCB1, and Thompson Sampling run in shadow mode. Azure SQL owns operational state and aggregate feature snapshots, Cosmos DB owns decisions and outcomes, and Blob Storage owns versioned artifacts.

The complete contracts, feature catalog, algorithm calculations, LGPD controls, training gates, rollback process, and Azure population preflight are defined in [`docs/recommendation-system.md`](docs/recommendation-system.md). The generation path for each choice model is documented in [`docs/choice-model-generation.md`](docs/choice-model-generation.md).

Supporting diagrams:

- [`docs/recommendation-system-overview.svg`](docs/recommendation-system-overview.svg) - system and storage ownership.
- [`docs/recommendation-decision-flow.svg`](docs/recommendation-decision-flow.svg) - eligibility, ranking, presentation, and feedback.
- [`docs/recommendation-training-lifecycle.svg`](docs/recommendation-training-lifecycle.svg) - batch evaluation and promotion.
- [`docs/recommendation-privacy-boundary.svg`](docs/recommendation-privacy-boundary.svg) - blocked and approved data boundaries.
- [`docs/choice-model-generation-pipeline.svg`](docs/choice-model-generation-pipeline.svg) - choice model generation pipeline.
- [`docs/choice-model-selection-flow.svg`](docs/choice-model-selection-flow.svg) - runtime choice selection flow.
- [`docs/choice-model-policy-comparison.svg`](docs/choice-model-policy-comparison.svg) - policy comparison by evidence source and serving role.

## ECloe Market Surface

![ECloe Market overview](docs/ecloe-market-overview.svg)

ECloe Market is the implemented marketplace surface inside the demo application. It owns catalog browsing, cart state, checkout creation, pending orders, recommendation telemetry, and aggregation of commerce signals before an authorized channel calls ECloe Engine.

| Concern | Status | Architecture boundary |
|:---|:---|:---|
| Catalog and cart presentation | Implemented | Simulated products, categories, product details, cart state, and checkout entry. |
| Transactional source of truth | Implemented | Azure SQL stores catalog, inventory, carts, checkout sessions, orders, order items, interactions, and outbox rows. |
| Checkout consistency | Implemented | Memory and SQL repositories revalidate price, stock, idempotency, and order state before committing. |
| Event publication | Planned for demo | Market writes domain state and an outbox row in the same Azure SQL transaction; the Outbox Publisher polls committed rows and publishes to Azure Service Bus. |
| Recommendation handoff | Planned for demo | Authorized orchestration sends minimized context and eligible offers to ECloe Engine after upstream eligibility. |
| Real payment, fraud, risk, credit, pricing automation, and eligibility decisions | Out of scope | These must not be presented as ECloe Market or ECloe Engine responsibilities. |

Detailed data model, checkout transaction, events, file flow, and Azure direction are documented in [`docs/ecloe-market.md`](docs/ecloe-market.md).

Supporting ECloe Market diagrams:

- [`docs/ecloe-market-overview.svg`](docs/ecloe-market-overview.svg) - planned ECloe Market overview.
- [`docs/ecloe-market-class-diagram.svg`](docs/ecloe-market-class-diagram.svg) - ECloe Market domain and repository class diagram.
- [`docs/ecloe-market-checkout-flow.svg`](docs/ecloe-market-checkout-flow.svg) - planned checkout and order flow.
- [`docs/ecloe-market-file-flow.svg`](docs/ecloe-market-file-flow.svg) - planned file and data flow.

## ECloe Pay Surface

![ECloe Pay overview](docs/ecloe-pay-overview.svg)

ECloe Pay is the implemented wallet surface inside the demo application. It obtains a real recommendation from ECloe Engine, presents one selected eligible benefit, records backend-mapped interactions, and persists Pay-owned state through the repository boundary.

| Concern | Status | Architecture boundary |
|:---|:---|:---|
| Wallet presentation | Implemented | Simulated UI state for balance, cashback, savings goals, benefits, and accepted-offer status. |
| Engine decision | Implemented | Pay stores the `decision_id` and selected benefit returned by the shared Engine service. |
| Real-ready Azure SQL account model | Planned for demo | The next Pay implementation step uses `ecloe_validation` schemas for identity, wallet ledger, payments, rewards, audit, and integration while keeping `master` free of application tables. |
| Reward registration | Implemented | `POST /v2/feedback` records slate-bound telemetry and backend-mapped terminal outcomes; v1 remains compatible. |
| Technical evidence | Planned for demo | Technical mode may show request ID, decision ID, event ID, policy, artifact, latency, and excluded fields. |
| Real payment account integration | Future | Requires governed wallet, identity, consent, security, and operations systems. |
| Credit, fraud, risk, compliance, and eligibility decisions | Out of scope | These remain upstream and must not be presented as ECloe Pay or ECloe Engine responsibilities. |

Detailed screen inventory, data contract, reward mapping, Azure direction, and the real-ready Azure SQL implementation plan are documented in [`docs/ecloe-pay.md`](docs/ecloe-pay.md).

Supporting ECloe Pay diagrams:

- [`docs/ecloe-pay-overview.svg`](docs/ecloe-pay-overview.svg) - planned ECloe Pay overview.
- [`docs/ecloe-pay-transfer-flow.svg`](docs/ecloe-pay-transfer-flow.svg) - planned wallet benefit transfer flow.
- [`docs/ecloe-pay-simplified-relationship.svg`](docs/ecloe-pay-simplified-relationship.svg) - simplified relationship between channels, services, and state stores.

## Components

| Component | Responsibility | Key files/paths |
|:---|:---|:---|
| Configuration | Loads local `.env` settings, data paths, Kaggle dataset slug, file names, seed, and Azure placeholders. | `src/core/config.py`, `.env.example` |
| ECloe Market | Implemented simulated marketplace for product browsing, catalog, cart, checkout, pending orders, inventory, and recommendation signals. | `src/market/`, `src/demo/ecloe_market/`, `docs/ecloe-market.md` |
| ECloe Pay | Implemented simulated digital wallet for payment context, Engine-selected benefits, accepted-offer status, and interactions. | `src/demo/ecloe_pay/`, `docs/ecloe-pay.md` |
| ECloe Engine | Adaptive decision layer that ranks eligible offers using marketplace-finance context and simulated conversion likelihood. | `src/bandits/`, `src/evaluation/`, `src/engine/` |
| Local Engine API | Exposes the implemented health, policy, purchase-likelihood, and decision endpoints. | `src/api/` |
| Data ingestion | Downloads the configured Hillstrom Kaggle dataset into `data/raw/hillstrom.csv`. | `src/data/download.py` |
| Data schema | Defines accepted source columns, minimized context columns, allowed actions, rewards, and blocked columns. | `src/data/schemas.py` |
| Data processing | Normalizes columns, validates required fields, maps `segment -> action`, maps `conversion -> reward`, removes blocked modeling fields, and writes processed CSV output. | `src/data/process.py`, `tests/test_data_process.py` |
| Data validation | Produces `reports/data_validation.json` with missing values, duplicate count, action distribution, conversion rate, blocked columns, and validity status. | `src/data/validate.py`, `tests/test_data_validate.py` |
| Storage contracts | Defines Azure settings, Cosmos DB document shapes, and promoted Blob artifact loading for decision serving. | `src/storage/`, `src/engine/artifact_sources.py` |
| Offline policy layer | Implements Baseline, Epsilon-Greedy, UCB, and Thompson Sampling evaluation. | `src/bandits/`, `src/evaluation/` |
| Notebooks | Reproduce the essential data, validation, training, evaluation, and cloud-reference stages. | `notebooks/` |
| Marketplace-finance demo | Planned app simulation showing ECloe Market behavior, ECloe Pay context, eligible offers, recommendations, and reward events. | `docs/demo-interface.md`, `docs/ecloe-market.md`, `docs/ecloe-pay.md` |
| Documentation | Central delivery documentation, diagrams, contracts, governance, model card, and demo script. | `README.md`, `docs/` |

## Data / ML Pipeline Flow

![MLOps lifecycle](docs/mlops-lifecycle.svg)

The MVP pipeline is intentionally small:

1. Download the Kaggle Hillstrom email-campaign dataset.
2. Process the dataset into minimized context, action, and reward columns.
3. Validate that no blocked columns are present in the processed dataset.
4. Interpret the rows as a public proxy for marketplace-finance context, eligible action, and reward.
5. Run the deterministic baseline and adaptive policies on the same offline sequence.
6. Write local policy metrics and artifacts under `reports/policy_training/`.
7. Train the lightweight purchase-likelihood validator.
8. Select the policy for the Golden Set and local Engine API.

The detailed model-by-model generation flow is described in [`docs/choice-model-generation.md`](docs/choice-model-generation.md), including baseline ranking, content affinity, likelihood smoothing, Epsilon-Greedy, UCB1, and Thompson Sampling.

## API Security and Observability

![API security and observability flow](docs/api-security-observability-flow.svg)

The API runtime now has an explicit operational perimeter. Business routes validate Microsoft Entra ID bearer tokens and route scopes in cloud environments, while local disabled authentication is limited to loopback execution. The middleware applies trusted host checks, explicit CORS origins, payload limits, request rate limits, and concurrency limits before the route handler executes.

The customer-facing Flask BFF uses a separate Microsoft Entra External ID registration. It completes Authorization Code with PKCE server-side, maps `(issuer, sub)` to an HMAC identity key, and issues only an opaque application session. First login transactionally provisions a deterministic synthetic profile, wallet account, and transaction history in Azure SQL; no token, password, real e-mail address, or real financial identifier is stored. Setup and operations are documented in [`docs/azure-customer-authentication.md`](docs/azure-customer-authentication.md).

Every request emits structured telemetry with `request_id`, `trace_id`, route, status, latency, and safe decision metadata such as `decision_id` and `policy_version` when available. Full `customer_context` payloads are intentionally excluded from access logs. OpenTelemetry instrumentation can export traces to Application Insights when the optional observability dependencies and connection string are configured.

Continuous assurance is enforced through CI gates for Ruff, pytest with coverage, dependency audit, OpenAPI compatibility, CodeQL, and secret scanning.

## Target Azure Architecture

![Azure architecture flow](docs/azure-architecture-flow.svg)

The target cloud architecture keeps the MVP low-consumption:

| Layer | MVP option | Role |
|:---|:---|:---|
| Runtime | Azure Container Apps first, App Service Linux fallback | Runs the FastAPI ECloe Engine container with Managed Identity. |
| Artifacts | Azure Blob Storage | Stores immutable training runs and a mutable `promoted/current.json` pointer. |
| Events | Cosmos DB Serverless | Stores decision events, reward events, and policy versions. The existing decision/reward containers use `/customer_id` as partition key, populated only with ECloe's pseudonymized subject key. |
| Secrets | Azure Key Vault | Keeps Kaggle, storage, and runtime credentials outside code. |
| Observability | Application Insights | Tracks latency, error rate, decision count, and reward count. |

AKS, Azure Machine Learning, API Management, and Azure AI Search are future enterprise options. They should not block the Datathon MVP.

The current Cosmos DB Serverless setup, promoted artifact layout, and deployment path are documented in [`docs/cloud-setup.md`](docs/cloud-setup.md), [`docs/artifact-promotion.md`](docs/artifact-promotion.md), and [`docs/azure-deployment.md`](docs/azure-deployment.md).

## API and Event Contracts

The implemented local Engine API, planned reward payloads, and privacy boundaries are documented in [`docs/api-contract.md`](docs/api-contract.md). The practical marketplace-finance scenario is documented in [`docs/marketplace-finance-use-case.md`](docs/marketplace-finance-use-case.md), the ECloe Market marketplace surface is documented in [`docs/ecloe-market.md`](docs/ecloe-market.md), and the ECloe Pay wallet surface is documented separately in [`docs/ecloe-pay.md`](docs/ecloe-pay.md). The MVP includes local policy training, purchase-likelihood artifact generation, artifact validation, and promotion documented in [`docs/training-workflow.md`](docs/training-workflow.md).

## Key Design Decisions

- **Local-first execution** - keeps the project easy to run and avoids unnecessary cloud cost during the Datathon.
- **Public Kaggle data only** - avoids real customer data and makes the experiment reproducible.
- **Marketplace-finance framing** - positions ECloe as the decision layer connecting commerce behavior and digital wallet actions.
- **Named product surfaces** - ECloe Market and ECloe Pay make the demo concrete while ECloe Engine remains reusable.
- **Eligibility stays upstream** - ECloe only ranks actions already allowed by marketplace, wallet, risk, and compliance systems.
- **Minimized Hillstrom context** - keeps `history_segment` but drops raw monetary `history` and `zip_code` from the modeling dataset.
- **Explicit action/reward mapping** - uses `segment` as the observed campaign action and `conversion` as the binary reward.
- **Compare policies instead of merging them** - Baseline, Epsilon-Greedy, UCB, and Thompson Sampling are evaluated as separate strategies.
- **Use Thompson Sampling as the initial candidate** - it fits binary rewards and handles uncertainty with documented Beta priors.
- **Separate serving from offline promotion** - `/v1/policies/current` is the source of truth for the online serving strategy, while offline artifacts document the promoted policy for review.
- **Estimate likelihood lightly** - purchase probability uses smoothed offline conversion rates and fallbacks instead of a heavy classifier.
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
│   ├── api/              # Local FastAPI surface for ECloe Engine
│   ├── bandits/          # Offline decision policies
│   ├── core/             # Settings and environment variable loading
│   ├── data/             # Kaggle download, schema, processing, and validation
│   ├── engine/           # Purchase likelihood and decision services
│   ├── evaluation/       # Policy training and report generation
│   └── storage/          # Azure settings and expected document shapes
├── tests/                # Automated tests
├── Architecture.md       # Detailed architecture and pipeline documentation
├── pyproject.toml        # Dependencies and package configuration
├── .env.example          # Environment variable template
└── README.md             # Central project documentation
```

## Limitations

- The repository does not yet include MLflow runs or a full marketplace-finance user interface.
- The target Azure services are architectural guidance, not deployed infrastructure.
- Offline simulation is useful for engineering validation, but it is not production evidence.
- Purchase likelihood is based on public proxy data and should not be interpreted as real banking purchase propensity.
- A regulated production deployment would require legal, security, privacy, model risk, and operational reviews.
