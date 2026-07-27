targetScope = 'resourceGroup'

@description('Short environment suffix for globally unique names.')
param environmentName string = 'mvp'

@description('Azure region. Prefer chilecentral when Container Apps is available.')
param location string = resourceGroup().location

@description('Container image tag to deploy, for example <acr>.azurecr.io/ecloe-engine:<git-sha>.')
param containerImage string

@description('Existing Cosmos DB account name.')
param cosmosAccountName string = 'ecloe5cosmos1266cl'

@description('Existing Cosmos DB database name.')
param cosmosDatabaseName string = 'ecloe'

@description('Microsoft Entra tenant ID.')
param entraTenantId string

@description('Microsoft Entra client/application ID for the API.')
param entraClientId string

@description('Subject-key salt should come from a secure deployment parameter or Key Vault reference.')
@secure()
param subjectKeySalt string

@description('Container App external ingress port.')
param targetPort int = 8000

var unique = uniqueString(resourceGroup().id, environmentName)
var acrName = toLower('ecloeacr${unique}')
var storageName = toLower('ecloeart${unique}')
var logName = 'ecloe-log-${environmentName}'
var appInsightsName = 'ecloe-ai-${environmentName}'
var envName = 'ecloe-aca-env-${environmentName}'
var appName = 'ecloe-engine-${environmentName}'
var artifactContainerName = 'ecloe-artifacts'

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource artifactContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: '${storage.name}/default/${artifactContainerName}'
  properties: {
    publicAccess: 'None'
  }
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

resource managedEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnv.id
    configuration: {
      activeRevisionsMode: 'Multiple'
      ingress: {
        external: true
        targetPort: targetPort
      }
      secrets: [
        {
          name: 'subject-key-salt'
          value: subjectKeySalt
        }
      ]
      registries: [
        {
          server: acr.properties.loginServer
          identity: 'system'
        }
      ]
    }
    template: {
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
      containers: [
        {
          name: 'ecloe-engine'
          image: containerImage
          env: [
            {
              name: 'APP_ENVIRONMENT'
              value: 'cloud'
            }
            {
              name: 'API_HOST'
              value: '0.0.0.0'
            }
            {
              name: 'AUTH_MODE'
              value: 'entra_id'
            }
            {
              name: 'ENTRA_TENANT_ID'
              value: entraTenantId
            }
            {
              name: 'ENTRA_CLIENT_ID'
              value: entraClientId
            }
            {
              name: 'ENTRA_AUDIENCE'
              value: 'api://${entraClientId}'
            }
            {
              name: 'SUBJECT_KEY_SALT'
              secretRef: 'subject-key-salt'
            }
            {
              name: 'DECISION_REPOSITORY_MODE'
              value: 'cosmos'
            }
            {
              name: 'AZURE_COSMOS_AUTH_MODE'
              value: 'managed_identity'
            }
            {
              name: 'AZURE_COSMOS_ENDPOINT'
              value: 'https://${cosmosAccountName}.documents.azure.com:443/'
            }
            {
              name: 'AZURE_COSMOS_DATABASE'
              value: cosmosDatabaseName
            }
            {
              name: 'ARTIFACT_SOURCE'
              value: 'azure_blob'
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT_URL'
              value: storage.properties.primaryEndpoints.blob
            }
            {
              name: 'AZURE_BLOB_CONTAINER_ARTIFACTS'
              value: artifactContainerName
            }
            {
              name: 'AZURE_ARTIFACT_PROMOTION_BLOB'
              value: 'promoted/current.json'
            }
            {
              name: 'ARTIFACT_CACHE_DIR'
              value: '/tmp/ecloe/artifacts'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
    }
  }
}

resource blobReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, app.name, 'Storage Blob Data Reader')
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, app.name, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output containerAppName string = app.name
output containerAppUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output acrLoginServer string = acr.properties.loginServer
output storageAccountName string = storage.name
output artifactContainer string = artifactContainerName
output managedIdentityPrincipalId string = app.identity.principalId
output cosmosDataContributorCommand string = 'scripts/grant_cosmos_data_contributor.ps1 -AccountName ${cosmosAccountName} -DatabaseName ${cosmosDatabaseName} -PrincipalId ${app.identity.principalId}'
