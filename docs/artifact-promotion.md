# Artifact Promotion

ECloe separates artifact generation from artifact promotion. A training run is reusable only after validation writes a manifest and the manifest is published to Azure Blob Storage.

## Validate

```bash
python -m src.evaluation.validate_artifacts
```

The validator checks metrics, selected policy, Golden Set, purchase-likelihood model, data-validation status, and SHA-256 checksums. It writes `reports/policy_training/artifact_manifest.json`.

## Publish

```bash
python scripts/publish_artifacts_to_blob.py
```

Publishing uploads artifacts to `runs/<run_id>/`. The upload is idempotent: an existing run blob is downloaded and verified by checksum instead of overwritten.

## Promote

```bash
python scripts/publish_artifacts_to_blob.py --promote
```

Promotion updates `promoted/current.json` to point at an immutable run manifest. It should be used only after tests, artifact validation, and human review pass.

Recommendation artifacts are promoted independently per surface. The feedback job writes
`reports/recommendation/<surface>/<run_id>/`; after review, publish it with:

```powershell
python scripts/publish_recommendation_artifacts.py --run-dir reports/recommendation/market/<run_id> --surface market --promote
python scripts/publish_recommendation_artifacts.py --run-dir reports/recommendation/pay/<run_id> --surface pay --promote
```

The mutable pointers are `promoted/market/current.json` and
`promoted/pay/current.json`. A failed runtime reload keeps the previously loaded
surface snapshot and does not change either pointer.

## Publish Training Results to Cosmos DB

Cosmos publication is separate from Blob artifact promotion. Use it when the validated offline metrics and policy metadata need to be available in the cloud event store:

```bash
python scripts/publish_training_results_to_cosmos.py
```

The command publishes to Cosmos DB database `ecloe`, container `policy_versions`, with partition key `/policy_name`. For the latest confirmed run, publication produced 5 documents: 4 `policy_version` documents and 1 `training_run` document.

Confirmed counts:

| Container | Documents |
|:---|---:|
| `policy_versions` | 5 |
| `decisions` | 0 |
| `rewards` | 0 |

`decisions` and `rewards` are intentionally empty after training publication because they store runtime API events, not offline training artifacts.

## Roll Back

Rollback changes `promoted/current.json` back to a previous `run_id`, then verifies `/readyz` and `/v1/policies/current`. Application revision rollback is independent from artifact rollback.

## Current Validated Manifest

Latest local manifest:

| Field | Value |
|:---|:---|
| `run_id` | `train-20260727T211636Z-43b893e` |
| `git_commit` | `43b893e20072e6833787f2b4d3d484e56be8c89b` |
| `dataset_sha256` | `252576717b865f1ca247309735ea538845fbbc0d8193a21ab83d7c1e83d8ae79` |
| `python_version` | `3.14.6` |
| `seed` | `42` |
| `generated_at` | `2026-07-27T21:16:36Z` |

This run has been validated locally, but it has not been published to Azure Blob Storage from this workstation.
