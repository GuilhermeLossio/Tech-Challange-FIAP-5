# Azure Infra Implementation Plan

## Objective

Prepare the ECloe Engine cloud runtime in Azure Container Apps using the existing Azure subscription and resource group.

Target runtime:

| Setting | Value |
|:---|:---|
| Subscription | `Azure for Students` |
| Resource group | `FIAPTechChallange5` |
| Region | `chilecentral` |
| Runtime | Azure Container Apps |
| Container App | `ecloe-engine-mvp` |
| Container Apps environment | `ecloe-demo-aca-env` |
| Container registry | `ecloedemo1266.azurecr.io` |
| Cosmos account | `ecloe5cosmos1266cl` |
| Cosmos database | `ecloe` |
| Artifact container | `ecloe-artifacts` |
| Promotion pointer | `promoted/current.json` |

## Current Gaps

The pre-implementation inspection found these gaps:

| Area | Current state | Required state |
|:---|:---|:---|
| Container App | No Engine Container App exists | `ecloe-engine-mvp` deployed |
| Container Apps environment | One environment already exists | Reuse `ecloe-demo-aca-env` due subscription regional quota |
| Bicep/ACR | Template created a new ACR | Template uses existing `ecloedemo1266` |
| Region | Resource group default is `eastus` | Runtime resources in `chilecentral` |
| ACR images | Existing ACRs have no repositories | `ecloe-engine:<tag>` pushed |
| Artifacts | No `ecloe-artifacts` container | Promoted run in Blob Storage |
| Cosmos permissions | User has data-plane role | Container App identity has data-plane role |
| Cosmos TTL | `decisions` and `rewards` TTL unset | TTL set to `157680000` seconds |

## Implementation Sequence

1. Update infrastructure code and deployment workflow.
2. Validate Bicep syntax.
3. Run a Bicep what-if against `FIAPTechChallange5`.
4. Configure GitHub environment `mvp` with required variables and secrets.
5. Trigger the GitHub Actions `Deploy` workflow for environment `mvp`.
6. Grant the resulting Container App managed identity Cosmos DB data contributor access on `/dbs/ecloe`.
7. Publish local `reports/policy_training` artifacts to the Bicep-created storage account and promote `promoted/current.json`.
8. Enable TTL on the Cosmos `decisions` and `rewards` containers.
9. Validate Container App health, Blob pointer, role assignments, and logs.
10. Write the final application report.

## Required GitHub Environment

Environment: `mvp`

Variables:

```text
AZURE_RESOURCE_GROUP=FIAPTechChallange5
AZURE_LOCATION=chilecentral
ACR_NAME=ecloedemo1266
ACR_LOGIN_SERVER=ecloedemo1266.azurecr.io
CONTAINERAPPS_ENVIRONMENT=ecloe-demo-aca-env
AZURE_COSMOS_ACCOUNT=ecloe5cosmos1266cl
AZURE_COSMOS_DATABASE=ecloe
```

Secrets:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
ENTRA_CLIENT_ID
FLASK_SECRET_KEY
SUBJECT_KEY_SALT
RATE_LIMIT_REDIS_URL
```

Secret values must not be committed or copied into reports.

## Rollback

- Application rollback: redeploy the prior `ecloe-engine:<tag>` image through the same workflow or switch the active Container Apps revision.
- Artifact rollback: update `ecloe-artifacts/promoted/current.json` to a prior immutable `runs/<run_id>/artifact_manifest.json`.
- Infrastructure rollback: delete only the newly created Engine runtime resources after confirming no other workload uses them.
