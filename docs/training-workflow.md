# Training Workflow

## Purpose

ECloe trains decision behavior through offline policy simulation. It does not train a supervised classifier in this stage. The goal is to compare a deterministic baseline against adaptive bandit policies on the same processed Hillstrom sequence and select the policy with the strongest local evidence.

## Input

Default command:

```bash
python -m src.evaluation.run
```

Prepare data and train in one command:

```bash
python -m src.evaluation.run --prepare-data
```

Low-consumption training run:

```bash
python -m src.evaluation.run --max-rows 5000
```

Export recorded Engine decisions and rewards from Cosmos DB into a reusable training CSV and run the offline evaluation in one command:

```bash
python scripts/retrain_from_cosmos_events.py
```

The export-only command is also available when you want to inspect the CSV before training:

```bash
python scripts/export_cosmos_events_for_training.py
```

Default input:

```text
data/processed/hillstrom_processed.csv
```

Cosmos-derived input:

```text
data/processed/cosmos_training_events.csv
```

`--prepare-data` downloads the configured Kaggle dataset, processes it, validates it, and then uses the processed file for training. The default command does not perform network access. The Cosmos export command reads the configured `decisions` and `rewards` containers, joins each rewarded decision to its reward event, maps the selected offer back to the offline action space, and writes a binary reward CSV for later evaluation.

The processed dataset must contain:

| Column | Purpose |
|:---|:---|
| `row_id` | Deterministic non-linkable row identifier |
| `action` | Observed Hillstrom campaign action |
| `reward` | Binary conversion reward |
| Context columns | Minimized fields used for Golden Set explanation |

## Policies Compared

| Policy | Role |
|:---|:---|
| `baseline` | Deterministic control that selects the action with the best train reward rate |
| `epsilon_greedy` | Simple adaptive policy with fixed exploration probability |
| `ucb` | Optimistic adaptive policy using uncertainty bonuses |
| `thompson_sampling` | Bayesian adaptive policy using Beta priors for binary rewards |

The policies are compared, not merged. Each policy receives the same evaluation row order and the same deterministic reward simulation table.

## Evaluation Method

The runner uses a deterministic `70% train / 30% evaluation` split. The train split estimates historical reward rates by action. The evaluation split uses those rates to build a seeded binary reward table for all actions. This keeps the comparison reproducible while avoiding leakage from blocked fields.

For low-consumption experiments, use `--max-rows` to cap the number of processed rows read into the training simulation. This is useful for quick local checks, notebooks, and constrained machines. Full local evaluation can still run without the cap.

Selection rule:

```text
max cumulative_reward, then min cumulative_regret, then min exploration_rate
```

## Outputs

Default output folder:

```text
reports/policy_training/
```

Generated files:

| File | Description |
|:---|:---|
| `metrics.json` | Reward rates and policy metrics |
| `metrics.csv` | Tabular policy metric summary |
| `policy_versions.json` | Evaluated policy metadata for audit and promotion |
| `selected_policy.json` | Winning policy and selection rule |
| `golden_set_recommendations.json` | Five deterministic examples for Demo Day review |
| `policy_state_thompson_sampling.json` | Thompson Sampling alpha/beta state |
| `purchase_likelihood_model.json` | Smoothed conversion-rate artifact used by the local ECloe Engine API |
| `artifact_manifest.json` | Checksums, run ID, dataset hash, Python version, and artifact inventory |

## Interpreting `selected_policy.json`

`selected_policy.json` is the local promotion candidate. It identifies the policy selected by the offline comparison and records the metrics used for that selection. It is not production approval evidence by itself; it should be reviewed together with the Golden Set, model card, governance notes, and known limitations.

## Purchase Likelihood Validator

The command below trains only the lightweight purchase-likelihood validator:

```bash
python -m src.engine.train_likelihood
```

The validator is not a supervised classifier. It estimates purchase or conversion likelihood from smoothed offline rates by action and by available context. If an exact context is not available, it falls back from contextual rates to action rates and then to the global conversion rate.

The local API uses this artifact to return likelihood estimates for eligible offers and to support the `/v1/decisions` endpoint.

## Artifact Validation

Validate the generated training outputs before promotion:

```bash
python -m src.evaluation.validate_artifacts
```

The validator checks the policy metrics, selected offline policy, purchase-likelihood artifact, Golden Set, data-validation status, and file checksums. It writes:

```text
reports/policy_training/artifact_manifest.json
```

Publish a validated run to Azure Blob Storage:

```bash
python scripts/publish_artifacts_to_blob.py --promote
```

Use `--promote` only after review. Promotion updates `promoted/current.json` to point to the immutable `runs/<run_id>/artifact_manifest.json` path; it does not overwrite previous runs.

## Publish Training Results to Cosmos DB

After artifact validation, the training results can also be published to Cosmos DB for audit and reuse by cloud governance views:

```bash
python scripts/publish_training_results_to_cosmos.py
```

The command writes to database `ecloe`, container `policy_versions`, whose partition key is `/policy_name`. The latest confirmed publication wrote 5 documents:

| Document type | Count | Purpose |
|:---|---:|:---|
| `policy_version` | 4 | One document per evaluated policy: `baseline`, `epsilon_greedy`, `ucb`, and `thompson_sampling` |
| `training_run` | 1 | Run-level manifest, selected policy, dataset checksum, and artifact summary |

Current confirmed container counts:

| Container | Documents | Interpretation |
|:---|---:|:---|
| `policy_versions` | 5 | Training results were published successfully |
| `decisions` | 0 | Expected until the API receives runtime decision requests |
| `rewards` | 0 | Expected until the API receives runtime reward events |

Training publication is a post-training step. It does not retrain the policies and it does not create operational decision or reward events.

## Latest Validated Run

The latest local run used the full processed Hillstrom dataset without `--max-rows`.

| Field | Value |
|:---|:---|
| Processed rows | 57,438 |
| Training rows | 40,206 |
| Evaluation rows | 17,232 |
| Selected offline policy | `baseline` |
| Artifact run ID | `train-20260727T211636Z-43b893e` |
| Dataset SHA-256 | `252576717b865f1ca247309735ea538845fbbc0d8193a21ab83d7c1e83d8ae79` |
| Python version | `3.14.6` |
| Seed | `42` |

Policy comparison:

| Policy | Rounds | Cumulative reward | Conversion rate | Cumulative regret | Exploration rate |
|:---|:---|:---|:---|:---|:---|
| `baseline` | 17,232 | 252 | 0.014624 | 0.0 | 0.0 |
| `epsilon_greedy` | 17,232 | 225 | 0.013057 | 15.830237 | 0.204445 |
| `ucb` | 17,232 | 182 | 0.010562 | 58.341888 | 0.605153 |
| `thompson_sampling` | 17,232 | 237 | 0.013753 | 20.800918 | 0.185469 |

The result supports keeping `baseline` as the offline promoted policy for this run while retaining adaptive policies as challengers for future online reward evidence.

## MLflow

MLflow remains a future enhancement. The current implementation intentionally uses local reports only to keep the Datathon MVP lightweight and easy to run.

The current runner is low-consumption by design:

- no cloud dependency during training;
- no MLflow process required;
- small JSON/CSV reports only;
- optional row cap through `--max-rows`;
- deterministic seed for repeatable comparisons.
