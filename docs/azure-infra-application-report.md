# Azure Infra Application Report

Date: 2026-08-13 America/Sao_Paulo

## Summary

The ECloe Engine Azure infrastructure was partially applied and documented.

Applied successfully:

- Created the pre-implementation plan in `docs/azure-infra-implementation-plan.md`.
- Updated `docs/azure-deployment.md` with the real deployment path.
- Updated `infra/bicep/main.bicep` and compiled `infra/bicep/main.json`.
- Updated `.github/workflows/deploy.yml` to pass `location`, `acrName`, and `containerAppsEnvironmentName`.
- Created Microsoft Entra app registration `ecloe-engine-api`.
- Exposed Engine API delegated scopes: `policy:read`, `decision:read`, `decision:write`, `reward:write`.
- Created Storage account `ecloeartyh2t5whbdcwdc`.
- Created private Blob container `ecloe-artifacts`.
- Created Application Insights component `ecloe-ai-mvp`.
- Created Container App resource `ecloe-engine-mvp`.
- Granted Cosmos DB data-plane access to the Container App managed identity.
- Granted `AcrPull` and `Storage Blob Data Reader` to the Container App managed identity.
- Granted `Storage Blob Data Contributor` to the signed-in user for artifact publication.
- Regenerated and validated policy artifacts.
- Published and promoted Blob artifacts.
- Enabled TTL on Cosmos `decisions` and `rewards`.

Not fully completed:

- The Engine Container App does not have a running revision yet because `ecloedemo1266.azurecr.io/ecloe-engine:eeb377f` is not present in ACR.
- Public smoke tests could not run because the Container App has no FQDN until a revision is created.

## Infrastructure Applied

Azure context:

| Item | Value |
|:---|:---|
| Subscription | `Azure for Students` |
| Subscription ID | `1266f60d-5c9a-45f6-8f39-9c23494c87d3` |
| Tenant ID | `11dbbfe2-89b8-4549-be10-cec364e59551` |
| Resource group | `FIAPTechChallange5` |
| Region | `chilecentral` |

Created or reused resources:

| Resource | Type | State |
|:---|:---|:---|
| `ecloedemo1266` | Azure Container Registry | Existing, empty |
| `ecloe-demo-aca-env` | Container Apps Environment | Existing |
| `ecloeartyh2t5whbdcwdc` | Storage account | Created |
| `ecloe-artifacts` | Blob container | Created, private |
| `ecloe-ai-mvp` | Application Insights | Created |
| `ecloe-engine-mvp` | Container App | Created, revision pending |
| `ecloe5cosmos1266cl/ecloe` | Cosmos DB | Existing |
| `ecloe-engine-api` | Microsoft Entra app registration | Created, scopes exposed |

Container App identity:

```text
9899ed8d-1928-4cf9-b004-88ffeb5a7340
```

Assigned permissions:

| Principal | Permission | Scope |
|:---|:---|:---|
| Container App identity | `Cosmos DB Built-in Data Contributor` | `ecloe5cosmos1266cl/dbs/ecloe` |
| Container App identity | `AcrPull` | `ecloedemo1266` |
| Container App identity | `Storage Blob Data Reader` | `ecloeartyh2t5whbdcwdc` |
| Signed-in user | `Storage Blob Data Contributor` | `ecloeartyh2t5whbdcwdc` |

## Commands Executed

Validation:

```powershell
az bicep build --file infra\bicep\main.bicep
.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_artifact_sources.py tests/test_api_main.py
az deployment group what-if --resource-group FIAPTechChallange5 --template-file infra\bicep\main.bicep --parameters environmentName=mvp location=chilecentral acrName=ecloedemo1266 containerAppsEnvironmentName=ecloe-demo-aca-env containerImage=ecloedemo1266.azurecr.io/ecloe-engine:eeb377f entraTenantId=<tenant-id> entraClientId=<api-client-id> subjectKeySalt=<secret> cosmosAccountName=ecloe5cosmos1266cl cosmosDatabaseName=ecloe --result-format ResourceIdOnly
```

Azure application:

```powershell
az ad app create --display-name ecloe-engine-api --sign-in-audience AzureADMyOrg
az ad app update --id ea3a2333-dced-4cc3-9b67-f833390eefa5 --identifier-uris api://ea3a2333-dced-4cc3-9b67-f833390eefa5
az storage account create --resource-group FIAPTechChallange5 --name ecloeartyh2t5whbdcwdc --location chilecentral --sku Standard_LRS --kind StorageV2 --allow-blob-public-access false --min-tls-version TLS1_2
az extension add --name application-insights --yes
az monitor app-insights component create --app ecloe-ai-mvp --location chilecentral --resource-group FIAPTechChallange5 --application-type web
az storage container create --account-name ecloeartyh2t5whbdcwdc --name ecloe-artifacts --auth-mode login --public-access off
.\scripts\grant_cosmos_data_contributor.ps1 -PrincipalId 9899ed8d-1928-4cf9-b004-88ffeb5a7340
az role assignment create --assignee-object-id 9899ed8d-1928-4cf9-b004-88ffeb5a7340 --assignee-principal-type ServicePrincipal --role AcrPull --scope <acr-scope>
az role assignment create --assignee-object-id 9899ed8d-1928-4cf9-b004-88ffeb5a7340 --assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" --scope <storage-scope>
az cosmosdb sql container update --resource-group FIAPTechChallange5 --account-name ecloe5cosmos1266cl --database-name ecloe --name decisions --ttl 157680000
az cosmosdb sql container update --resource-group FIAPTechChallange5 --account-name ecloe5cosmos1266cl --database-name ecloe --name rewards --ttl 157680000
```

Artifacts:

```powershell
.venv\Scripts\python.exe -m src.evaluation.run --prepare-data
.venv\Scripts\python.exe -m src.evaluation.validate_artifacts
.venv\Scripts\python.exe -m scripts.publish_artifacts_to_blob --artifact-dir reports\policy_training --promote
```

Promoted artifact pointer:

```json
{
  "run_id": "train-20260814T000729Z-eeb377f",
  "manifest_blob": "runs/train-20260814T000729Z-eeb377f/artifact_manifest.json",
  "promoted_at": "2026-08-14T00:07:33Z"
}
```

## Validation Results

Passed:

- `az bicep build --file infra\bicep\main.bicep`
- `az deployment group what-if`
- `pytest tests/test_config.py tests/test_artifact_sources.py tests/test_api_main.py`: 41 passed
- `pytest tests/test_config.py tests/test_ecloe_external_identity.py tests/test_api_main.py`: 46 passed
- `python -m src.evaluation.validate_artifacts`
- Blob `ecloe-artifacts/promoted/current.json` exists
- Cosmos TTL:
  - `decisions`: `157680000`
  - `rewards`: `157680000`
- Cosmos DB role assignment exists for Container App identity
- `AcrPull` and `Storage Blob Data Reader` role assignments exist for Container App identity

Blocked:

- `az acr build` failed because ACR Tasks are not supported for the `chilecentral` ACR location by the current Azure CLI/API path.
- Creating an auxiliary ACR in `eastus` or `brazilsouth` failed due subscription region policy.
- Docker, Podman, `gh`, and GitHub token environment variables were not available locally.
- ACR `ecloedemo1266` still has no repositories, so `ecloe-engine:eeb377f` is missing.
- `ecloe-engine-mvp` has a FQDN and revision, but the revision is stuck in `ImagePullBackOff` because `ecloe-engine:eeb377f` is missing.
- Azure CLI token acquisition for `api://ea3a2333-dced-4cc3-9b67-f833390eefa5/policy:read` returned `AADSTS65001 consent_required`; interactive user/admin consent is required before live protected endpoint testing.

## Next Required Step

Publish the image `ecloedemo1266.azurecr.io/ecloe-engine:eeb377f` by one of these paths:

1. Run the GitHub Actions `Deploy` workflow after pushing the workflow/Bicep changes and configuring the `mvp` environment variables/secrets documented in `docs/azure-deployment.md`.
2. Install Docker locally, then build and push:

```powershell
az acr login --name ecloedemo1266
docker build --build-arg VCS_REF=eeb377fb52a7a091a7a2a6ed432317b65c4838ec --build-arg VERSION=eeb377f -t ecloedemo1266.azurecr.io/ecloe-engine:eeb377f .
docker push ecloedemo1266.azurecr.io/ecloe-engine:eeb377f
```

After the image exists, rerun:

```powershell
az deployment group create --resource-group FIAPTechChallange5 --template-file infra\bicep\main.bicep --parameters environmentName=mvp location=chilecentral acrName=ecloedemo1266 containerAppsEnvironmentName=ecloe-demo-aca-env containerImage=ecloedemo1266.azurecr.io/ecloe-engine:eeb377f entraTenantId=<tenant-id> entraClientId=ea3a2333-dced-4cc3-9b67-f833390eefa5 subjectKeySalt=<secret> cosmosAccountName=ecloe5cosmos1266cl cosmosDatabaseName=ecloe
```

Then validate:

```powershell
az containerapp show --resource-group FIAPTechChallange5 --name ecloe-engine-mvp
Invoke-WebRequest https://<fqdn>/livez
Invoke-WebRequest https://<fqdn>/readyz
```
