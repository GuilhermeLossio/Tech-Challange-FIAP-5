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
| `decisions` | `/customer_id` | Decision events returned by the policy |
| `rewards` | `/customer_id` | Conversion or reward events linked to decisions |
| `policy_versions` | `/policy_name` | Offline metrics and policy approval metadata |

## Manual Environment Variables

Secrets must be filled manually in local `.env` or through a managed runtime configuration. Do not commit secret values.

```text
AZURE_COSMOS_ENDPOINT=https://ecloe5cosmos1266cl.documents.azure.com:443/
AZURE_COSMOS_DATABASE=ecloe
AZURE_COSMOS_CONTAINER_DECISIONS=decisions
AZURE_COSMOS_CONTAINER_REWARDS=rewards
AZURE_COSMOS_CONTAINER_POLICIES=policy_versions
```

Use `AZURE_COSMOS_KEY` only for local experiments when Managed Identity is not available. For Azure App Service or Container Apps, prefer Managed Identity and Cosmos DB data-plane role assignment.

## Region Notes

The subscription policy allowed only a limited set of regions. Serverless creation failed in `northcentralus`, `canadacentral`, and `southcentralus` due to regional capacity constraints. `chilecentral` accepted the Serverless account.

## Cost Controls

- Use Serverless for the MVP event store.
- Keep training reports local unless cloud upload is explicitly needed.
- Avoid AKS, Azure Machine Learning, API Management, and Azure AI Search for this stage.
- Delete unused experimental Cosmos accounts if they were left in failed provisioning state.
