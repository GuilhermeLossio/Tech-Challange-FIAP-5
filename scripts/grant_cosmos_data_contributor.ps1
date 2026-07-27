param(
    [string]$ResourceGroup = "FIAPTechChallange5",
    [string]$AccountName = "ecloe5cosmos1266cl",
    [string]$DatabaseName = "ecloe"
)

$ErrorActionPreference = "Stop"

$principalId = az ad signed-in-user show --query id -o tsv
if (-not $principalId) {
    throw "Azure CLI did not return the signed-in user object ID. Run 'az login' first."
}

$roleDefinitionId = az cosmosdb sql role definition list `
    --resource-group $ResourceGroup `
    --account-name $AccountName `
    --query "[?roleName=='Cosmos DB Built-in Data Contributor'].id | [0]" `
    -o tsv

if (-not $roleDefinitionId) {
    throw "Could not find the Cosmos DB Built-in Data Contributor role definition."
}

$scope = "/dbs/$DatabaseName"

az cosmosdb sql role assignment create `
    --resource-group $ResourceGroup `
    --account-name $AccountName `
    --role-definition-id $roleDefinitionId `
    --principal-id $principalId `
    --scope $scope

Write-Host "Granted Cosmos DB data contributor access on $AccountName$scope to signed-in Azure CLI principal $principalId."
