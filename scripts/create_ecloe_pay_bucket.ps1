param(
    [string]$ResourceGroup = "FIAPTechChallange5",
    [string]$Location = "chilecentral",
    [string]$BaseStorageAccountName = "ecloepaydemo",
    [string]$ContainerName = "ecloe-pay-demo-artifacts",
    [string]$Sku = "Standard_LRS"
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Invoke-AzJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $json = & az @Arguments --only-show-errors -o json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }

    if ([string]::IsNullOrWhiteSpace($json)) {
        return $null
    }

    return $json | ConvertFrom-Json
}

function Test-StorageAccountInResourceGroup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $null = & az storage account show --resource-group $ResourceGroup --name $Name --only-show-errors -o none 2>$null
    $ErrorActionPreference = $previousErrorActionPreference
    return $LASTEXITCODE -eq 0
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI was not found. Install Azure CLI and run 'az login' before this script."
}

$null = & az account show --only-show-errors -o none
if ($LASTEXITCODE -ne 0) {
    throw "Azure CLI is not logged in. Run 'az login' and retry."
}

$null = & az group show --name $ResourceGroup --only-show-errors -o none
if ($LASTEXITCODE -ne 0) {
    throw "Resource group '$ResourceGroup' was not found."
}

$normalizedBaseName = ($BaseStorageAccountName.ToLowerInvariant() -replace "[^a-z0-9]", "")
if ($normalizedBaseName.Length -lt 3) {
    throw "Base storage account name must contain at least 3 letters or numbers."
}
if ($normalizedBaseName.Length -gt 18) {
    $normalizedBaseName = $normalizedBaseName.Substring(0, 18)
}

$storageAccountName = $null
$storageAccountExists = $false
$candidateNames = @($normalizedBaseName)
for ($attempt = 1; $attempt -le 8; $attempt++) {
    $candidateNames += "$normalizedBaseName$(Get-Random -Minimum 100000 -Maximum 999999)"
}

foreach ($candidate in $candidateNames) {
    if (Test-StorageAccountInResourceGroup -Name $candidate) {
        $storageAccountName = $candidate
        $storageAccountExists = $true
        break
    }

    $availability = Invoke-AzJson -Arguments @("storage", "account", "check-name", "--name", $candidate)
    if ($availability.nameAvailable -eq $true) {
        $storageAccountName = $candidate
        break
    }
}

if ([string]::IsNullOrWhiteSpace($storageAccountName)) {
    throw "Could not find an available Azure Storage Account name from base '$normalizedBaseName'."
}

if (-not $storageAccountExists) {
    $null = & az storage account create `
        --resource-group $ResourceGroup `
        --name $storageAccountName `
        --location $Location `
        --sku $Sku `
        --kind StorageV2 `
        --https-only true `
        --min-tls-version TLS1_2 `
        --allow-blob-public-access false `
        --only-show-errors `
        -o none
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create storage account '$storageAccountName'."
    }
}

$null = & az storage container create `
    --account-name $storageAccountName `
    --name $ContainerName `
    --auth-mode login `
    --public-access off `
    --only-show-errors `
    -o none
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create private container '$ContainerName' in '$storageAccountName'."
}

Write-Output "ECloe Pay bucket is ready."
Write-Output "Resource group: $ResourceGroup"
Write-Output "Location: $Location"
Write-Output "Storage account: $storageAccountName"
Write-Output "Container: $ContainerName"
Write-Output "Access: private"
