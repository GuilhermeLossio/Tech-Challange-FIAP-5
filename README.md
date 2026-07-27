# ECloe - Datathon 7MLET
> **Low-cost next-best-action engine for integrated marketplace and digital wallet ecosystems.**

ECloe is a Machine Learning Engineering MVP that compares deterministic and adaptive decision policies for recommending the next best eligible action in a marketplace-finance journey. The product story is split into **ECloe Market**, a simulated marketplace, **ECloe Pay**, a simulated digital wallet, and **ECloe Engine**, the adaptive decision layer between them. It shows how marketplace behavior and wallet context can guide offers, messages, or benefits without making credit, fraud, or eligibility decisions. The active data-preparation foundation is the public Kaggle Hillstrom email-campaign dataset, processed into minimized context, action, and reward columns for offline bandit evaluation.

## Table of Contents

- [Capabilities](#capabilities)
- [Business Problem](#business-problem)
- [Architecture](#architecture)
- [Demo Interface](#demo-interface)
- [ECloe Market](#ecloe-market)
- [ECloe Pay](#ecloe-pay)
- [Dataset](#dataset)
- [Training Strategy](#training-strategy)
- [API Examples](#api-examples)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Evaluation Metrics](#evaluation-metrics)
- [Latest Local Results](#latest-local-results)
- [Validation Evidence](#validation-evidence)
- [Golden Set](#golden-set)
- [Deployment Strategy](#deployment-strategy)
- [Team Identification](#team-identification)
- [Related Docs](#related-docs)
- [Limitations](#limitations)

---

## Capabilities

| Capability | Description |
|:---|:---|
| Offline experimentation | Uses Kaggle campaign rows as an offline simulation environment. |
| ECloe Market | Simulates marketplace behavior such as category interest, cart events, checkout, and recurrence. |
| ECloe Pay | Simulates wallet context and eligible financial actions such as cashback, savings goals, and account benefits. |
| Marketplace-finance framing | Maps commerce behavior and wallet context to eligible financial actions. |
| Data minimization | Drops raw purchase amount and ZIP-level fields from the modeling dataset. |
| Adaptive recommendation | Compares Baseline, Epsilon-Greedy, UCB, and Thompson Sampling policies. |
| Local policy training | Runs deterministic offline policy simulation with local reports. |
| Purchase likelihood validator | Estimates simulated conversion probability for eligible offers through ECloe Engine. |
| Local Engine API | Exposes liveness, readiness, policy, likelihood-estimate, decision, and reward endpoints with FastAPI routers. |
| Evaluation-first delivery | Measures conversion rate, cumulative reward, regret, and exploration rate before selecting a policy. |
| Golden Set validation | Contains 5 deterministic examples for explainable Demo Day validation. |
| Low-consumption architecture | Prioritizes local execution and small Azure services instead of enterprise infrastructure. |

---

## Business Problem

Digital marketplaces connected to payment accounts need to decide which eligible financial action should be shown in moments such as home browsing, checkout, wallet engagement, or post-purchase follow-up. Static rules and long A/B tests can waste traffic, react slowly to behavior changes, and make responsible personalization harder to operate.

ECloe frames this as an adaptive experimentation problem: explore enough to learn, exploit the best known option when evidence is strong, and keep sensitive financial decisions outside the model. Upstream marketplace, wallet, compliance, and risk systems decide eligibility; ECloe only chooses which eligible action should be shown next.

Target product framing:

```text
ECloe Market behavior + ECloe Pay context -> ECloe Engine -> next best eligible action
```

See [`docs/marketplace-finance-use-case.md`](./docs/marketplace-finance-use-case.md) for the practical application scenario.

---

## Architecture

![Decision flow](docs/decision-flow.svg)

The MVP flow is intentionally simple: Kaggle data is downloaded and processed locally as a proxy for historical marketplace-finance interactions, offline policies are evaluated against the same simulated customer sequence, and the winning policy can later be exposed through a script, notebook, or lightweight demo interface. See [`Architecture.md`](./Architecture.md) for the full component breakdown, target Azure architecture, and pipeline flow.

Supporting diagrams:

- [`docs/decision-flow.svg`](./docs/decision-flow.svg) - decision and reward loop.
- [`docs/demo-interface-flow.svg`](./docs/demo-interface-flow.svg) - planned demo interface layer.
- [`docs/ecloe-market-overview.svg`](./docs/ecloe-market-overview.svg) - planned ECloe Market overview.
- [`docs/ecloe-market-checkout-flow.svg`](./docs/ecloe-market-checkout-flow.svg) - planned ECloe Market checkout and order flow.
- [`docs/ecloe-market-file-flow.svg`](./docs/ecloe-market-file-flow.svg) - planned ECloe Market file and data flow.
- [`docs/ecloe-pay-overview.svg`](./docs/ecloe-pay-overview.svg) - planned ECloe Pay overview.
- [`docs/ecloe-pay-transfer-flow.svg`](./docs/ecloe-pay-transfer-flow.svg) - planned ECloe Pay transfer flow.
- [`docs/ecloe-pay-simplified-relationship.svg`](./docs/ecloe-pay-simplified-relationship.svg) - simplified ECloe Pay relationships.
- [`docs/azure-architecture-flow.svg`](./docs/azure-architecture-flow.svg) - target Azure service map.
- [`docs/mlops-lifecycle.svg`](./docs/mlops-lifecycle.svg) - offline evaluation and promotion lifecycle.
- [`docs/api-security-observability-flow.svg`](./docs/api-security-observability-flow.svg) - API security, telemetry, and CI gates.

---

## Demo Interface

Status: **Planned for demo**.

The planned ECloe Demo is one simulated web application with three areas: **ECloe Market** for marketplace browsing and checkout, **ECloe Pay** for wallet benefits and accepted-offer status, and **ECloe Control Room** for the technical journey. The interface will consume the existing **ECloe Engine** API through a planned demo backend-for-frontend that aggregates context, simulates upstream eligibility, calls the decision endpoint, and registers reward events.

Short journey:

```text
Demo persona -> ECloe Market -> eligible offers -> ECloe Engine decision -> ECloe Pay interaction -> reward event -> ECloe Control Room summary
```

Eligibility, risk, compliance, and business rules remain upstream. ECloe Engine only ranks one eligible offer from the request. See [`docs/demo-interface.md`](./docs/demo-interface.md) for the planned screens, states, API calls, and presentation flow.

---

## ECloe Market

Status: **Planned for demo**.

ECloe Market is documented as the simulated marketplace surface for catalog browsing, cart management, checkout, order creation, and behavior-signal aggregation. It uses Azure SQL as the planned transactional source of truth, outbox events for reliable async publication, and ECloe Engine only after eligible offers have already been determined upstream.

Detailed ECloe Market scope, data model, checkout transaction, event flow, Azure direction, implementation sequence, and SVG diagrams are documented separately in [`docs/ecloe-market.md`](./docs/ecloe-market.md).

---

## ECloe Pay

Status: **Planned for demo**.

ECloe Pay is documented as the simulated wallet surface for the demo. It displays wallet benefits, reuses the checkout decision returned by ECloe Engine, lets the user open, dismiss, or accept the selected eligible offer, and registers the interaction through the implemented reward endpoint. The Pay surface does not approve credit, calculate eligibility, process real payments, or trigger immediate model learning.

Detailed ECloe Pay scope, screens, data boundaries, reward flow, Azure direction, and SVG diagrams are documented separately in [`docs/ecloe-pay.md`](./docs/ecloe-pay.md).

---

## Dataset

The main dataset is Kaggle [`kevin-hillstrom-minethatdata-e-mailanalytics` by bofulee](https://www.kaggle.com/datasets/bofulee/kevin-hillstrom-minethatdata-e-mailanalytics).

Data-preparation usage rules:

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

## Training Strategy

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
| Thompson Sampling | Adaptive challenger | Bayesian exploration with Beta priors for binary rewards. |

The algorithms are compared, not merged into one model. Offline evaluation selects an offline promoted policy for review, while the current online serving strategy remains the strategy returned by `/v1/policies/current`. The Engine API must not be described as serving Thompson Sampling unless the implementation actually selects offers with that strategy at request time.

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

Export reusable decision/reward events from Cosmos DB and retrain from that CSV in one command:

```bash
python scripts/retrain_from_cosmos_events.py
```

Expected training outputs:

```text
reports/policy_training/metrics.json
reports/policy_training/metrics.csv
reports/policy_training/policy_versions.json
reports/policy_training/selected_policy.json
reports/policy_training/golden_set_recommendations.json
reports/policy_training/policy_state_thompson_sampling.json
reports/policy_training/purchase_likelihood_model.json
reports/policy_training/artifact_manifest.json
```

See [`docs/training-workflow.md`](./docs/training-workflow.md) for the full offline training flow.

Validate generated artifacts before publishing or deploying:

```bash
python -m src.evaluation.validate_artifacts
```

Publish and optionally promote artifacts to Azure Blob Storage:

```bash
python scripts/publish_artifacts_to_blob.py --promote
```

Publish the validated training results to Cosmos DB for reuse by cloud governance and audit views:

```bash
python scripts/publish_training_results_to_cosmos.py
```

This command writes to Cosmos DB database `ecloe`, container `policy_versions`. The confirmed publication for run `train-20260727T211636Z-43b893e` created 5 documents: 4 `policy_version` documents and 1 `training_run` document. `decisions` and `rewards` remain empty by design until the API receives live decision and reward events.

Generate only the lightweight purchase-likelihood validator:

```bash
python -m src.engine.train_likelihood
```

Run the local ECloe Engine API after the training artifacts exist:

```bash
python -m src.api.main
```

Local endpoints:

| Method | Path | Scope | Purpose |
|:---|:---|:---|:---|
| `GET` | `/livez` | None | Liveness check for the HTTP process. |
| `GET` | `/readyz` | None | Readiness check that requires serving artifacts to be loaded. |
| `GET` | `/v1/policies/current` | `policy:read` | Current serving strategy and artifact metadata. |
| `POST` | `/v1/likelihood-estimates` | `decision:read` | Estimated purchase/conversion probability by eligible offer. |
| `POST` | `/v1/purchase-likelihood` | `decision:read` | Deprecated alias for `/v1/likelihood-estimates`. |
| `POST` | `/v1/decisions` | `decision:write` | Recommended eligible offer with likelihood, policy, and reason codes. |
| `POST` | `/v1/rewards` | `reward:write` | Append-only reward event ingestion linked to an existing decision. |

Cloud runtime must use Microsoft Entra ID bearer tokens. `AUTH_MODE=disabled` is accepted only for local loopback execution with `API_HOST=127.0.0.1`.
`POST /v1/decisions` accepts `Idempotency-Key`; repeating the same key for the same authenticated subject returns the original persisted decision without creating a duplicate event.
`POST /v1/rewards` uses `event_id` as an idempotency key; duplicate reward events return the original accepted response.
Local development persists decision events to `reports/decision_events.jsonl`; cloud runtime must use Cosmos DB with Managed Identity.
Cloud runtime must also use `ARTIFACT_SOURCE=azure_blob` so the API loads the promoted artifact run from Azure Blob Storage and fails readiness when the promoted manifest or checksums are invalid.

---

## API Examples

Local example with `AUTH_MODE=disabled` and the API running on `127.0.0.1:8000`:

```bash
curl -X POST "http://127.0.0.1:8000/v1/decisions" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-checkout-001" \
  -d '{
    "request_id": "req_demo_001",
    "customer_context": {
      "channel": "Web",
      "history_segment": "2) $100 - $200",
      "newbie": 1
    },
    "eligible_offers": [
      "cashback_recurring_purchase",
      "savings_goal",
      "financial_education"
    ]
  }'
```

Example decision response:

```json
{
  "decision_id": "dec_123",
  "offer_id": "cashback_recurring_purchase",
  "purchase_likelihood": 0.1375,
  "policy": "likelihood_ranker",
  "policy_version": "likelihood-v1",
  "reason_codes": [
    "highest_validated_purchase_likelihood",
    "contextual_conversion_rate"
  ]
}
```

Reward registration example:

```bash
curl -X POST "http://127.0.0.1:8000/v1/rewards" \
  -H "Content-Type: application/json" \
  -d '{
    "decision_id": "dec_123",
    "event_id": "evt_demo_001",
    "event_type": "conversion",
    "reward": 1.0,
    "occurred_at": "2026-07-05T15:00:00Z"
  }'
```

See [`docs/api-contract.md`](./docs/api-contract.md) for the complete request and response contract, validation rules, and cloud authentication requirements.

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

The current structure is consistent for a Python data/ML MVP. The policy training and notebook layers are now implemented; future work should add `src/demo/` when the recommendation interface is created.

---

## Getting Started

### Prerequisites

- Python 3.14.6, matching `pyproject.toml` and GitHub Actions.
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

MLflow remains a future experiment-tracking enhancement.

### Configure `.env`

```bash
cp .env.example .env
```

Required Kaggle variables:

```text
KAGGLE_USERNAME=
KAGGLE_KEY=
```

### Run Data Preparation

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
python -m src.engine.train_likelihood
python -m src.api.main
mlflow ui
```

`python -m src.evaluation.run`, `python -m src.engine.train_likelihood`, and `python -m src.api.main` are implemented for local reports and serving. MLflow UI remains a planned future step.

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

## Latest Local Results

The latest local training report is [`reports/policy_training/metrics.json`](./reports/policy_training/metrics.json). It compares all policies on the same 17,232 simulated evaluation rounds after a deterministic 70/30 split of 57,438 validated processed rows.

| Policy | Rounds | Cumulative reward | Conversion rate | Cumulative regret | Exploration rate |
|:---|:---|:---|:---|:---|:---|
| Baseline | 17,232 | 252 | 1.4624% | 0.000000 | 0.0000% |
| Epsilon-Greedy | 17,232 | 225 | 1.3057% | 15.830237 | 20.4445% |
| UCB | 17,232 | 182 | 1.0562% | 58.341888 | 60.5153% |
| Thompson Sampling | 17,232 | 237 | 1.3753% | 20.800918 | 18.5469% |

The local promotion rule selected `baseline` because it produced the highest cumulative reward, then the lowest regret and exploration rate. Thompson Sampling remains documented as an adaptive challenger, but it is not the promoted policy for this run.

In this offline Hillstrom simulation, the deterministic baseline outperformed adaptive policies on cumulative reward and regret. That is a useful MVP signal: the historical action-reward pattern is stable enough that exploration-heavy policies should remain challengers until more online reward evidence is collected from ECloe decisions and rewards.

Current validated artifact run:

| Field | Value |
|:---|:---|
| `run_id` | `train-20260727T211636Z-43b893e` |
| `git_commit` | `43b893e20072e6833787f2b4d3d484e56be8c89b` |
| `dataset_sha256` | `252576717b865f1ca247309735ea538845fbbc0d8193a21ab83d7c1e83d8ae79` |
| `python_version` | `3.14.6` |
| `seed` | `42` |
| `generated_at` | `2026-07-27T21:16:36Z` |

Confirmed Cosmos publication:

| Container | Documents | Expected meaning |
| :--- | ---: | :--- |
| `policy_versions` | 5 | Training publication succeeded: 4 policy versions and 1 training run summary |
| `decisions` | 0 | No runtime decisions have been submitted through the API yet |
| `rewards` | 0 | No runtime rewards have been submitted through the API yet |

Training results belong to `policy_versions`; operational API evidence belongs to `decisions` and `rewards`.

---

## Validation Evidence

Latest local validation evidence:

| Check | Result |
|:---|:---|
| Data validation | Passed, 57,438 rows, 11 columns, 0 duplicate rows, no blocked columns |
| Artifact validation | Passed, manifest generated at `reports/policy_training/artifact_manifest.json` |
| Ruff | Passed with `python -m ruff check src tests scripts` |
| Tests | `74 passed` |
| Coverage | `77.68%`, above the 70% gate |
| Dependency audit | `No known vulnerabilities found` |
| Bicep build | Passed for `infra/bicep/main.bicep` |

Pytest reported one local cache warning for `.pytest_cache`; it did not fail the test run or reduce coverage. Docker image validation is still pending because Docker is not installed in the current Windows workstation.

---

## Golden Set

The Golden Set contains 5 deterministic cases used to validate explainability of the recommendations during Demo Day. The current local artifact is [`reports/policy_training/golden_set_recommendations.json`](./reports/policy_training/golden_set_recommendations.json), generated from processed Hillstrom rows and the selected offline policy.

| Case | Context snapshot | Recommended action | Policy | Reason codes |
|:---|:---|:---|:---|:---|
| 1 | `channel=Web`, `history_segment=4) $350 - $500`, `newbie=1` | `mens_email` | `baseline` | `offline_reward_evidence`, `policy_comparison_winner` |
| 2 | `channel=Phone`, `history_segment=5) $500 - $750`, `newbie=1` | `mens_email` | `baseline` | `offline_reward_evidence`, `policy_comparison_winner` |
| 3 | `channel=Phone`, `history_segment=3) $200 - $350`, `newbie=0` | `mens_email` | `baseline` | `offline_reward_evidence`, `policy_comparison_winner` |
| 4 | `channel=Phone`, `history_segment=1) $0 - $100`, `newbie=0` | `mens_email` | `baseline` | `offline_reward_evidence`, `policy_comparison_winner` |
| 5 | `channel=Web`, `history_segment=2) $100 - $200`, `newbie=0` | `mens_email` | `baseline` | `offline_reward_evidence`, `policy_comparison_winner` |

These are simulated recommendations for demonstration. They are not approvals for credit, loans, limits, eligibility, fraud, risk, or regulated financial products.

---

## Deployment Strategy

The MVP should run locally first. A cloud demonstration should use a low-consumption Azure setup:

| Layer | Suggested service |
|:---|:---|
| Runtime | Azure Container Apps first, Azure App Service Linux fallback |
| Artifacts | Azure Blob Storage with immutable runs and `promoted/current.json` |
| Events | Existing Cosmos DB Serverless account `ecloe5cosmos1266cl` |
| Secrets | Azure Key Vault |
| Observability | Application Insights |

AKS, Azure Machine Learning, API Management, and Azure AI Search remain future options, not MVP prerequisites.

The current Cosmos DB Serverless setup is documented in [`docs/cloud-setup.md`](./docs/cloud-setup.md). The existing `decisions` and `rewards` containers use `/customer_id` as the partition key; ECloe stores the pseudonymized `subject_key` value there, not a direct customer identifier.

Cloud deployment assets are present in `Dockerfile`, `.github/workflows/deploy.yml`, and `infra/bicep/main.bicep`. Local image build and Azure deployment are pending until Docker is available and the artifact Blob container is published with the promoted run.

---

## Team Identification

FIAP submissions often require team members and RM identifiers in the central README. The repository currently identifies the project license holder as **Guilherme Ferreira Medeiros Lossio**, but no RM or full group roster was found in the tracked documentation. Add the final FIAP group/RM information here before the Demo Day submission if the challenge rubric requires it.

---

## Related Docs

- [`Architecture.md`](./Architecture.md) - Architecture, components, pipeline, and trade-offs.
- [`docs/api-contract.md`](./docs/api-contract.md) - Implemented ECloe Engine API contracts and reward payloads.
- [`docs/demo-interface.md`](./docs/demo-interface.md) - Planned ECloe Market, ECloe Pay, and ECloe Control Room interface.
- [`docs/ecloe-market.md`](./docs/ecloe-market.md) - Dedicated ECloe Market marketplace surface documentation.
- [`docs/ecloe-market-overview.svg`](./docs/ecloe-market-overview.svg) - ECloe Market overview diagram.
- [`docs/ecloe-market-checkout-flow.svg`](./docs/ecloe-market-checkout-flow.svg) - ECloe Market checkout and order flow diagram.
- [`docs/ecloe-market-file-flow.svg`](./docs/ecloe-market-file-flow.svg) - ECloe Market file and data flow diagram.
- [`docs/ecloe-pay.md`](./docs/ecloe-pay.md) - Dedicated ECloe Pay wallet surface documentation.
- [`docs/ecloe-pay-overview.svg`](./docs/ecloe-pay-overview.svg) - ECloe Pay overview diagram.
- [`docs/ecloe-pay-transfer-flow.svg`](./docs/ecloe-pay-transfer-flow.svg) - ECloe Pay transfer flow diagram.
- [`docs/ecloe-pay-simplified-relationship.svg`](./docs/ecloe-pay-simplified-relationship.svg) - ECloe Pay simplified relationship diagram.
- [`docs/marketplace-finance-use-case.md`](./docs/marketplace-finance-use-case.md) - Practical marketplace and digital wallet use case.
- [`docs/data-structure.md`](./docs/data-structure.md) - Local data folders and cloud storage conventions.
- [`docs/evaluation-plan.md`](./docs/evaluation-plan.md) - Offline evaluation and Golden Set expectations.
- [`docs/training-workflow.md`](./docs/training-workflow.md) - Implemented local policy training workflow.
- [`docs/cloud-setup.md`](./docs/cloud-setup.md) - Current low-consumption Azure Cosmos DB setup.
- [`docs/artifact-promotion.md`](./docs/artifact-promotion.md) - Artifact validation, Blob publication, promotion, and rollback.
- [`docs/azure-deployment.md`](./docs/azure-deployment.md) - Azure Container Apps deployment path and runtime settings.
- [`docs/runbook.md`](./docs/runbook.md) - Operational checks, readiness troubleshooting, and rollback.
- [`docs/model-card.md`](./docs/model-card.md) - Policy intent, metrics, risks, and approval criteria.
- [`docs/system-card.md`](./docs/system-card.md) - System behavior, boundaries, and guardrails.
- [`docs/demo-script.md`](./docs/demo-script.md) - Demo Day presentation flow.
- [`docs/`](./docs) - SVG diagrams and supporting documentation.

---

## Limitations

- The Kaggle dataset is public and does not represent real customers from a financial institution.
- MVP offers and future reward assumptions are simulated to enable policy comparison.
- Offline rewards approximate a real environment but do not replace controlled production testing.
- Purchase likelihood is an offline simulated estimate, not production evidence of real customer purchase intent.
- Sensitive decisions would require human review, regulatory validation, security, privacy, and continuous monitoring.
- The cloud architecture is a target deployment, not a requirement for running the local MVP.

---

## License

MIT License. See [LICENSE](LICENSE).
