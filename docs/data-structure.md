# Data Structure

This document describes the initial data layout for the Kaggle extraction stage and the Azure resources expected by the MVP.

## Local Folders

```text
data/
  raw/          # Original Kaggle files, ignored by git
  processed/    # Cleaned datasets, ignored by git
  golden_set/   # Future offline evaluation cases, ignored by git
reports/        # Generated EDA outputs, ignored by git
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

Use `ecloe-raw` for immutable Kaggle source files and `ecloe-processed` for cleaned datasets, synthetic datasets, golden sets, and evaluation artifacts.

## Azure Cosmos DB

Recommended database:

```text
ecloe
```

Recommended containers:

```text
decisions
rewards
policy_versions
```

Suggested partition keys:

| Container | Partition key | Purpose |
|-----------|---------------|---------|
| `decisions` | `/customer_id` | Decision events returned by the policy |
| `rewards` | `/customer_id` | Click or conversion events linked to a decision |
| `policy_versions` | `/policy_name` | Approved policy metadata and offline metrics |

The Python document shapes are defined in `src/storage/cosmos_documents.py`.
