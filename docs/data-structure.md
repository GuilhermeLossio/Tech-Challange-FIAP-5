# Data Structure

This document describes the initial data layout for Kaggle extraction, local evaluation, and the low-consumption Azure MVP target.

## Local Folders

```text
.
├── data/
│   ├── raw/              # Original Kaggle files, ignored by git
│   ├── processed/        # Cleaned datasets, ignored by git
│   └── golden_set/       # Five deterministic evaluation cases
└── reports/              # Generated EDA outputs, metrics, and experiment artifacts
```

The folders are committed with `.gitkeep` files, but generated datasets and reports are intentionally ignored.

## Environment Variables

Use `.env.example` as the template. Local secrets must stay in `.env`.

Kaggle requires:

```text
KAGGLE_USERNAME=
KAGGLE_KEY=
```

The code also accepts `KAGGLE_API_KEY` as a local alias for `KAGGLE_KEY`, but `KAGGLE_KEY` is the recommended Kaggle API name.

Default dataset configuration:

```text
KAGGLE_DATASET=bofulee/kevin-hillstrom-minethatdata-e-mailanalytics
RAW_FILENAME=hillstrom.csv
PROCESSED_FILENAME=hillstrom_processed.csv
REPORTS_DIR=reports
```

Etapa 1 writes:

```text
data/raw/hillstrom.csv
data/processed/hillstrom_processed.csv
reports/data_validation.json
```

## Azure Blob Storage

Recommended containers:

```text
ecloe-raw
ecloe-processed
```

Use `ecloe-raw` for immutable Kaggle source files and `ecloe-processed` for cleaned datasets, Golden Set files, metrics, and evaluation artifacts.

## Azure Event Store

For the MVP, use either Cosmos DB Serverless or a small PostgreSQL instance. The planned event collections/tables are:

```text
decisions
rewards
policy_versions
```

Suggested logical partitioning:

| Store | Partition or index | Purpose |
|-------|--------------------|---------|
| `decisions` | `subject_key` | Pseudonymized decision events returned by the executed strategy |
| `rewards` | `subject_key` | Click or conversion events linked to a decision |
| `policy_versions` | `policy_name` | Approved policy metadata and offline metrics |

Decision events persist `decision_id`, `request_id`, selected offer, executed policy, policy version, artifact version and checksum, reason codes, UTC timestamp, minimized context, optional `Idempotency-Key`, and a pseudonymized `subject_key`. Cosmos DB TTL should be enabled for event containers using `DECISION_EVENT_TTL_SECONDS`; the default MVP retention is 157,680,000 seconds, or approximately 5 years.

The Python document shapes for Cosmos DB are defined in `src/storage/cosmos_documents.py`.
Local development uses `DECISION_REPOSITORY_MODE=file` and writes JSONL decision events to `reports/decision_events.jsonl`. Cloud runtime must use `DECISION_REPOSITORY_MODE=cosmos`.

The current Azure Cosmos DB Serverless setup is documented in [`cloud-setup.md`](cloud-setup.md).
