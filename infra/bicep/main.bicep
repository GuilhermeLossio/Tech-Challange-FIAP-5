targetScope = 'resourceGroup'

@description('Short environment suffix for globally unique names.')
param environmentName string = 'mvp'

@description('Azure region. Prefer chilecentral when Container Apps is available.')
param location string = resourceGroup().location

@description('Container image tag to deploy, for example <acr>.azurecr.io/ecloe-engine:<git-sha>.')
param containerImage string

@description('Existing Azure Container Registry name that contains the deployed image.')
param acrName string = 'ecloedemo1266'

@description('Existing Azure Container Apps environment name reused by the Engine runtime.')
param containerAppsEnvironmentName string = 'ecloe-demo-aca-env'

@description('Existing Cosmos DB account name.')
param cosmosAccountName string = 'ecloe5cosmos1266cl'

@description('Existing Cosmos DB database name.')
param cosmosDatabaseName string = 'ecloe'

@description('Existing Azure SQL logical server name for ECloe Pay demo persistence.')
param ecloePaySqlServerName string = 'ecloe-sql-1266'

@description('Existing Azure SQL database name for ECloe Pay demo persistence.')
param ecloePaySqlDatabaseName string = 'ecloe_validation'

@description('ODBC driver expected in the ECloe Pay runtime image.')
param ecloePaySqlDriver string = 'ODBC Driver 18 for SQL Server'

@description('Microsoft Entra tenant ID.')
param entraTenantId string

@description('Microsoft Entra client/application ID for the API.')
param entraClientId string

@description('Existing Key Vault containing runtime secrets.')
param keyVaultName string

@description('Key Vault secret name for the Flask signing key.')
param flaskSecretName string = 'ecloe-flask-secret-key'

@description('Key Vault secret name for the subject pseudonymization salt.')
param subjectKeySaltSecretName string = 'ecloe-subject-key-salt'

@description('Key Vault secret name containing the Redis URL.')
param rateLimitRedisSecretName string = 'ecloe-rate-limit-redis-url'

@description('Container App external ingress port.')
param targetPort int = 8000

var unique = uniqueString(resourceGroup().id, environmentName)
var storageName = toLower('ecloeart${unique}')
var appInsightsName = 'ecloe-ai-${environmentName}'
var appName = 'ecloe-engine-${environmentName}'
var artifactContainerName = 'ecloe-artifacts'
var keyVaultSecretIdentity = 'system'

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
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

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
}

resource ecloePaySqlServer 'Microsoft.Sql/servers@2023-08-01-preview' existing = {
  name: ecloePaySqlServerName
}

resource ecloePaySqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' existing = {
  parent: ecloePaySqlServer
  name: ecloePaySqlDatabaseName
}

resource managedEnv 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: containerAppsEnvironmentName
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
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
          identity: keyVaultSecretIdentity
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/${subjectKeySaltSecretName}'
        }
        {
          name: 'flask-secret-key'
          identity: keyVaultSecretIdentity
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/${flaskSecretName}'
        }
        {
          name: 'rate-limit-redis-url'
          identity: keyVaultSecretIdentity
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/${rateLimitRedisSecretName}'
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
              name: 'RATE_LIMIT_BACKEND'
              value: 'redis'
            }
            {
              name: 'RATE_LIMIT_REDIS_URL'
              secretRef: 'rate-limit-redis-url'
            }
            {
              name: 'FLASK_SECRET_KEY'
              secretRef: 'flask-secret-key'
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
              name: 'AZURE_ARTIFACT_PROMOTION_BLOB_MARKET'
              value: 'promoted/market/current.json'
            }
            {
              name: 'AZURE_ARTIFACT_PROMOTION_BLOB_PAY'
              value: 'promoted/pay/current.json'
            }
            {
              name: 'ARTIFACT_CACHE_DIR'
              value: '/tmp/ecloe/artifacts'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
            {
              name: 'ECLOE_PAY_DATABASE_MODE'
              value: 'azure_sql'
            }
            {
              name: 'ECLOE_PAY_SQL_SERVER'
              value: '${ecloePaySqlServer.name}${environment().suffixes.sqlServerHostname}'
            }
            {
              name: 'ECLOE_PAY_SQL_DATABASE'
              value: ecloePaySqlDatabase.name
            }
            {
              name: 'ECLOE_PAY_SQL_AUTH_MODE'
              value: 'managed_identity'
            }
            {
              name: 'ECLOE_PAY_SQL_DRIVER'
              value: ecloePaySqlDriver
            }
            {
              name: 'ECLOE_PAY_COOKIE_SECURE'
              value: 'true'
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

// Operational guardrails: 99.5% availability, p95 latency under 500 ms,
// and less than 1% failed requests. Action routing can be attached by the
// platform team through the alert resource IDs without changing the app.
resource failedRequestsAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'ecloe-${environmentName}-failed-requests'
  location: 'global'
  properties: {
    description: 'Alert when Engine failed requests exceed the 1% SLO budget.'
    severity: 2
    enabled: true
    scopes: [appInsights.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'failed-requests'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'requests/failed'
          operator: 'GreaterThan'
          threshold: 1
          timeAggregation: 'Count'
        }
      ]
    }
  }
}

resource latencyAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'ecloe-${environmentName}-latency'
  location: 'global'
  properties: {
    description: 'Alert when request latency breaches the 500 ms p95 SLO.'
    severity: 2
    enabled: true
    scopes: [appInsights.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'latency'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'requests/duration'
          operator: 'GreaterThan'
          threshold: 500
          timeAggregation: 'Average'
        }
      ]
    }
  }
}

resource availabilityAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'ecloe-${environmentName}-availability'
  location: 'global'
  properties: {
    description: 'Alert when availability falls below the 99.5% SLO.'
    severity: 1
    enabled: true
    scopes: [appInsights.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'availability'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'availabilityResults/availabilityPercentage'
          operator: 'LessThan'
          threshold: 995 / 10
          timeAggregation: 'Average'
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

resource keyVaultSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, app.name, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'
    )
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
output ecloePaySqlServer string = ecloePaySqlServer.properties.fullyQualifiedDomainName
output ecloePaySqlDatabase string = ecloePaySqlDatabase.name
