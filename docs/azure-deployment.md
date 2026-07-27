# Azure Deployment

ECloe Engine deploys as a low-cost Azure Container Apps runtime backed by promoted Blob artifacts and the existing Cosmos DB account `ecloe5cosmos1266cl`.

## Prerequisites

- Azure CLI authenticated with a deployment identity.
- GitHub Actions OIDC configured for the target subscription.
- Existing resource group `FIAPTechChallange5`.
- Existing Cosmos DB account `ecloe5cosmos1266cl`, database `ecloe`, and containers `decisions`, `rewards`, `policy_versions`.
- A validated and promoted artifact run in the `ecloe-artifacts` Blob container.

## Infrastructure

Deploy or update the runtime resources:

```bash
az deployment group create \
  --resource-group FIAPTechChallange5 \
  --template-file infra/bicep/main.bicep \
  --parameters environmentName=mvp containerImage=<acr>/ecloe-engine:<git-sha> entraTenantId=<tenant> entraClientId=<client> subjectKeySalt=<secret>
```

The template creates Azure Container Registry, Storage, `ecloe-artifacts`, Log Analytics, Application Insights, a Container Apps environment, and the ECloe Engine Container App with a system-assigned Managed Identity.

After deployment, grant the Container App identity Cosmos DB data-plane access:

```powershell
.\scripts\grant_cosmos_data_contributor.ps1 -PrincipalId <managed-identity-principal-id>
```

## Runtime Settings

Cloud runtime uses:

```text
APP_ENVIRONMENT=cloud
API_HOST=0.0.0.0
AUTH_MODE=entra_id
DECISION_REPOSITORY_MODE=cosmos
AZURE_COSMOS_AUTH_MODE=managed_identity
ARTIFACT_SOURCE=azure_blob
```

Do not configure `AUTH_MODE=disabled`, `AZURE_COSMOS_KEY`, or `AZURE_STORAGE_CONNECTION_STRING` in cloud.

## Smoke Tests

Run after deployment with a valid Entra ID bearer token:

```powershell
.\scripts\smoke_api.ps1 -BaseUrl https://<app-url> -BearerToken <token>
```

Also verify `GET /livez`, `GET /readyz`, logs, Cosmos persistence, and the promoted artifact version returned by `/v1/policies/current`.

## Current Deployment Status

Local validation is complete for the code, artifacts, dependency audit, and Bicep template. Azure deployment has not been executed from this workstation because Docker is not installed, so the container image could not be built or pushed locally.

Confirmed non-secret Azure state:

| Resource | Status |
|:---|:---|
| Subscription | `Azure for Students` |
| Resource group | `FIAPTechChallange5` |
| Cosmos account | `ecloe5cosmos1266cl` |
| Cosmos region | `Chile Central` |
| Cosmos endpoint | `https://ecloe5cosmos1266cl.documents.azure.com:443/` |
| Microsoft.App provider | Registered |

The existing Cosmos `decisions` and `rewards` containers use `/customer_id` as partition key. ECloe writes the pseudonymized subject key into that field and does not persist a direct customer identifier.

Training results were published separately with:

```bash
python scripts/publish_training_results_to_cosmos.py
```

The confirmed destination is Cosmos DB database `ecloe`, container `policy_versions`, partition key `/policy_name`. The confirmed state is:

| Container | Documents | Meaning |
|:---|---:|:---|
| `policy_versions` | 5 | 4 evaluated policy documents plus 1 training run document |
| `decisions` | 0 | No live API decision events have been persisted yet |
| `rewards` | 0 | No live API reward events have been persisted yet |

This is expected for a training-only publication. Runtime smoke tests should create and verify entries in `decisions` and `rewards`; training publication should not.
