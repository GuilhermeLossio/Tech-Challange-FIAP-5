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
| `decisions` | `decision_id` or customer/session hash | Decision events returned by the policy |
| `rewards` | `decision_id` | Click or conversion events linked to a decision |
| `policy_versions` | `policy_name` | Approved policy metadata and offline metrics |

The Python document shapes for Cosmos DB are defined in `src/storage/cosmos_documents.py`.
