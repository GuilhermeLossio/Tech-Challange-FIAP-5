# Cloud Setup

## Purpose

This document records the low-consumption Azure setup prepared for the ECloe MVP. The training workflow does not depend on cloud resources, but the target architecture can use Cosmos DB for decision, reward, and policy-version events.

## Cosmos DB

| Setting | Value |
|:---|:---|
| Resource group | `FIAPTechChallange5` |
| Account | `ecloe5cosmos1266cl` |
| API | Cosmos DB for NoSQL |
| Capacity mode | Serverless |
| Region | `Chile Central` |
| Database | `ecloe` |
| Endpoint | `https://ecloe5cosmos1266cl.documents.azure.com:443/` |

Containers:

| Container | Partition key | Purpose |
|:---|:---|:---|
| `decisions` | `/subject_key` | Pseudonymized decision events returned by the executed strategy |
| `rewards` | `/subject_key` | Conversion or reward events linked to decisions |
| `policy_versions` | `/policy_name` | Offline metrics and policy approval metadata |

Enable TTL on `decisions` and `rewards`. The MVP default is `DECISION_EVENT_TTL_SECONDS=157680000`, approximately 5 years.

## Manual Environment Variables

Secrets must be filled manually in local `.env` or through a managed runtime configuration. Do not commit secret values. Cloud runtime must use Microsoft Entra ID authentication for API access and Managed Identity for Cosmos DB.

```text
APP_ENVIRONMENT=cloud
API_HOST=0.0.0.0
AUTH_MODE=entra_id
ENTRA_TENANT_ID=<tenant-id>
ENTRA_CLIENT_ID=<api-application-client-id>
ENTRA_AUDIENCE=api://<api-application-client-id>
CORS_ALLOWED_ORIGINS=https://<approved-client-host>
TRUSTED_HOSTS=<approved-api-host>
SUBJECT_KEY_SALT=<non-default-pseudonymization-secret>
DECISION_EVENT_TTL_SECONDS=157680000
DECISION_REPOSITORY_MODE=cosmos
AZURE_COSMOS_ENDPOINT=https://ecloe5cosmos1266cl.documents.azure.com:443/
AZURE_COSMOS_AUTH_MODE=managed_identity
AZURE_COSMOS_DATABASE=ecloe
AZURE_COSMOS_CONTAINER_DECISIONS=decisions
AZURE_COSMOS_CONTAINER_REWARDS=rewards
AZURE_COSMOS_CONTAINER_POLICIES=policy_versions
```

Use `AZURE_COSMOS_KEY` only for local experiments when Managed Identity is not available. Azure App Service or Container Apps must use Managed Identity and a Cosmos DB data-plane role assignment. Startup is expected to fail in cloud when `AUTH_MODE=disabled`, `AZURE_COSMOS_KEY` is present, or `AZURE_COSMOS_AUTH_MODE` is not `managed_identity`.

For local Azure CLI authentication without storing a Cosmos DB master key, grant the signed-in user data-plane access:

```powershell
.\scripts\grant_cosmos_data_contributor.ps1
```

The script assigns the built-in Cosmos DB data contributor role on the `ecloe` database scope for `ecloe5cosmos1266cl`. It does not read or write `.env` and does not print or store Cosmos DB keys.

## Region Notes

The subscription policy allowed only a limited set of regions. Serverless creation failed in `northcentralus`, `canadacentral`, and `southcentralus` due to regional capacity constraints. `chilecentral` accepted the Serverless account.

## Cost Controls

- Use Serverless for the MVP event store.
- Keep training reports local unless cloud upload is explicitly needed.
- Avoid AKS, Azure Machine Learning, API Management, and Azure AI Search for this stage.
- Delete unused experimental Cosmos accounts if they were left in failed provisioning state.

## ECloe Pay Demo Artifact Bucket

ECloe Pay uses a dedicated private Azure Blob container for simulated Pay evidence such as demo-safe receipts, UI screenshots, and exported technical artifacts. It must not store real payment credentials, user account data, CPF, card data, or bank details.

Create or reuse the ECloe Pay storage resources with Azure CLI:

```powershell
.\scripts\create_ecloe_pay_bucket.ps1
```

Defaults:

| Setting | Value |
|:---|:---|
| Resource group | `FIAPTechChallange5` |
| Region | `chilecentral` |
| Storage account base name | `ecloepaydemo` |
| Container | `ecloe-pay-demo-artifacts` |
| Access level | Private |
| SKU | `Standard_LRS` |
| Minimum TLS | `TLS1_2` |

The script does not read or write `.env`. It requires an active Azure CLI login and creates the container with `--auth-mode login`.
