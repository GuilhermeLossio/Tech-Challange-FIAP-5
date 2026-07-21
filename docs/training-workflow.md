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

Default input:

```text
data/processed/hillstrom_processed.csv
```

`--prepare-data` downloads the configured Kaggle dataset, processes it, validates it, and then uses the processed file for training. The default command does not perform network access.

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

## Interpreting `selected_policy.json`

`selected_policy.json` is the local promotion candidate. It identifies the policy selected by the offline comparison and records the metrics used for that selection. It is not production approval evidence by itself; it should be reviewed together with the Golden Set, model card, governance notes, and known limitations.

## Purchase Likelihood Validator

The command below trains only the lightweight purchase-likelihood validator:

```bash
python -m src.engine.train_likelihood
```

The validator is not a supervised classifier. It estimates purchase or conversion likelihood from smoothed offline rates by action and by available context. If an exact context is not available, it falls back from contextual rates to action rates and then to the global conversion rate.

The local API uses this artifact to return likelihood estimates for eligible offers and to support the `/v1/decisions` endpoint.

## MLflow

MLflow remains a future enhancement. The current implementation intentionally uses local reports only to keep the Datathon MVP lightweight and easy to run.

The current runner is low-consumption by design:

- no cloud dependency during training;
- no MLflow process required;
- small JSON/CSV reports only;
- optional row cap through `--max-rows`;
- deterministic seed for repeatable comparisons.
