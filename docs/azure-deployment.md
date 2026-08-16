# Azure Deployment

ECloe Engine deploys as a low-cost Azure Container Apps runtime backed by promoted Blob artifacts and the existing Cosmos DB account `ecloe5cosmos1266cl`.

## Prerequisites

- Azure CLI authenticated with a deployment identity.
- GitHub Actions OIDC configured for the target subscription.
- Existing resource group `FIAPTechChallange5`.
- Existing Azure Container Registry `ecloedemo1266`.
- Existing Cosmos DB account `ecloe5cosmos1266cl`, database `ecloe`, and containers `decisions`, `rewards`, `policy_versions`.
- Existing Azure SQL server `ecloe-sql-1266`, database `ecloe_validation`, for optional ECloe Pay demo persistence.
- A Microsoft Entra External ID customer tenant, confidential web app registration, and e-mail/password user flow.
- An Azure Key Vault client secret reference readable by the demo Container App managed identity.
- A validated and promoted artifact run in the `ecloe-artifacts` Blob container.

## Infrastructure

Deploy or update the runtime resources:

```bash
az deployment group create \
  --resource-group FIAPTechChallange5 \
  --template-file infra/bicep/main.bicep \
  --parameters environmentName=mvp location=chilecentral acrName=ecloedemo1266 containerAppsEnvironmentName=ecloe-demo-aca-env containerImage=ecloedemo1266.azurecr.io/ecloe-engine:<git-sha> entraTenantId=<tenant> entraClientId=<client> keyVaultName=<key-vault-name>
```

The template uses the existing Azure Container Registry and existing Container Apps environment. It creates Storage, `ecloe-artifacts`, Application Insights, and the ECloe Engine Container App with a system-assigned Managed Identity.

The standard deployment path is the GitHub Actions `Deploy` workflow. The workflow builds `Dockerfile`, pushes `ecloe-engine:<tag>` to `ecloedemo1266.azurecr.io`, and then runs the Bicep deployment with `location=chilecentral`, `acrName=ecloedemo1266`, and `containerAppsEnvironmentName=ecloe-demo-aca-env`.

Required GitHub environment variables for `mvp`:

```text
AZURE_RESOURCE_GROUP=FIAPTechChallange5
AZURE_LOCATION=chilecentral
ACR_NAME=ecloedemo1266
ACR_LOGIN_SERVER=ecloedemo1266.azurecr.io
CONTAINERAPPS_ENVIRONMENT=ecloe-demo-aca-env
AZURE_COSMOS_ACCOUNT=ecloe5cosmos1266cl
AZURE_COSMOS_DATABASE=ecloe
AZURE_KEY_VAULT_NAME=<existing-key-vault-name>
ECLOE_ENGINE_TRUSTED_HOSTS=ecloe-engine-mvp.<container-apps-domain>
FLASK_SECRET_NAME=ecloe-flask-secret-key
SUBJECT_KEY_SALT_SECRET_NAME=ecloe-subject-key-salt
RATE_LIMIT_REDIS_SECRET_NAME=ecloe-rate-limit-redis-url
```

Required GitHub environment secrets for `mvp`:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
ENTRA_CLIENT_ID
```

The API workflow grants the Container App identity Cosmos DB data-plane access idempotently. The Key Vault must exist before the workflow starts and contain these secrets:

```text
ecloe-flask-secret-key
ecloe-subject-key-salt
ecloe-rate-limit-redis-url
```

The MVP Demo Web workflow uses `auth_mode=local_signup`, Azure SQL with Managed Identity,
and one replica. It requires these environment variables:

```text
ECLOE_KEY_VAULT_ID
ECLOE_PAY_SQL_SERVER
ECLOE_PAY_SQL_DATABASE
```

Set `ecloe-rate-limit-redis-url` to `memory://ecloe-mvp` for the single-replica MVP.
Before running the Demo Web workflow, apply `src/demo/ecloe_pay/schema.sql` and the Market
SQL schema with an Entra migration identity. Then grant the Container App identity access:

```powershell
python -m scripts.grant_ecloe_demo_sql_access --principal-id <managed-identity-object-id>
```

The script creates an idempotent contained user and grants runtime access only on the
`ecloe_pay` and `ecloe_market` schemas. The SQL firewall must allow the migration runner;
the deployment workflow does not widen the firewall automatically.

For a later External ID deployment, run `Deploy Demo Web` with `auth_mode=entra_external`
and additionally configure `ECLOE_WEB_ENTRA_AUTHORITY`, `ECLOE_WEB_ENTRA_CLIENT_ID`,
`ECLOE_WEB_ENTRA_CLIENT_SECRET_URI`, and `ECLOE_DEMO_WEB_BASE_URL`.

## Runtime Settings

Cloud runtime uses:

```text
APP_ENVIRONMENT=cloud
API_HOST=0.0.0.0
AUTH_MODE=entra_id
DECISION_REPOSITORY_MODE=cosmos
AZURE_COSMOS_AUTH_MODE=managed_identity
ARTIFACT_SOURCE=azure_blob
ECLOE_PAY_DATABASE_MODE=azure_sql
ECLOE_PAY_SQL_SERVER=ecloe-sql-1266.database.windows.net
ECLOE_PAY_SQL_DATABASE=ecloe_validation
ECLOE_PAY_SQL_AUTH_MODE=managed_identity
ECLOE_PAY_SQL_DRIVER=ODBC Driver 18 for SQL Server
ECLOE_PAY_COOKIE_SECURE=true
ECLOE_MARKET_DATABASE_MODE=azure_sql
ECLOE_WEB_AUTH_MODE=entra_external
ECLOE_WEB_ENTRA_AUTHORITY=https://<tenant-subdomain>.ciamlogin.com
ECLOE_WEB_ENTRA_CLIENT_ID=<client-id>
ECLOE_WEB_ENTRA_CLIENT_SECRET=<Container-Apps-secret-reference>
ECLOE_WEB_ENTRA_REDIRECT_URI=https://<demo-host>/auth/callback
ECLOE_WEB_ENTRA_POST_LOGOUT_REDIRECT_URI=https://<demo-host>/
```

Do not configure `AUTH_MODE=disabled`, `AZURE_COSMOS_KEY`, or `AZURE_STORAGE_CONNECTION_STRING` in cloud.
Do not configure `ECLOE_PAY_SQL_AUTH_MODE=entra_interactive` in cloud.
For ECloe Pay Azure SQL, grant the Container App managed identity only the minimum database rights needed for the `ecloe_pay` demo schema.
The demo deployment workflow additionally requires the non-secret GitHub variables `ECLOE_WEB_ENTRA_AUTHORITY`, `ECLOE_WEB_ENTRA_CLIENT_ID`, `ECLOE_WEB_ENTRA_CLIENT_SECRET_URI`, `ECLOE_KEY_VAULT_ID`, `ECLOE_DEMO_WEB_BASE_URL`, `ECLOE_PAY_SQL_SERVER`, and `ECLOE_PAY_SQL_DATABASE`. The client secret value remains in Key Vault. The deployment identity needs permission to create the Container App managed-identity role assignment on the Key Vault scope.

Apply `src/demo/ecloe_pay/schema.sql` with `python -m scripts.init_ecloe_pay_sql` before switching the web revision to External ID. Detailed tenant and rotation steps are in [`azure-customer-authentication.md`](azure-customer-authentication.md).

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

The Engine Bicep deployment now targets the existing `ecloedemo1266` ACR. This avoids creating a second ACR that cannot contain the image pushed by the workflow.

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
