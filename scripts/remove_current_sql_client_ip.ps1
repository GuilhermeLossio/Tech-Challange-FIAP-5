param(
    [string]$ResourceGroupName = "FIAPTechChallange5",
    [string]$ServerName = "ecloe-sql-1266",
    [string]$RuleName = "AllowCurrentClientIp"
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

function Invoke-AzNone {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $null = & az @Arguments --only-show-errors -o none
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
}

function Get-TargetSqlServer {
    $servers = @(Invoke-AzJson -Arguments @(
        "sql",
        "server",
        "list",
        "--query",
        "[?name=='$ServerName'].{name:name,resourceGroup:resourceGroup,fullyQualifiedDomainName:fullyQualifiedDomainName}"
    ))

    if ($servers.Count -ne 1) {
        throw "Expected exactly one Azure SQL server named '$ServerName', found $($servers.Count)."
    }
    if ($servers[0].resourceGroup -ne $ResourceGroupName) {
        throw "Server '$ServerName' was found in resource group '$($servers[0].resourceGroup)', not '$ResourceGroupName'."
    }

    return $servers[0]
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI was not found. Install Azure CLI and run 'az login' before this script."
}

Invoke-AzNone -Arguments @("account", "show")

$server = Get-TargetSqlServer
$existingRule = $null
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$existingRuleJson = & az sql server firewall-rule show `
    --resource-group $ResourceGroupName `
    --server $ServerName `
    --name $RuleName `
    --only-show-errors `
    -o json 2>$null
$ruleShowExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($ruleShowExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($existingRuleJson)) {
    $existingRule = $existingRuleJson | ConvertFrom-Json
}

if ($null -eq $existingRule) {
    Write-Output "Azure SQL firewall rule '$RuleName' was not found on $($server.fullyQualifiedDomainName). Nothing to remove."
    exit 0
}

Invoke-AzNone -Arguments @(
    "sql",
    "server",
    "firewall-rule",
    "delete",
    "--resource-group",
    $ResourceGroupName,
    "--server",
    $ServerName,
    "--name",
    $RuleName,
    "--yes"
)

Write-Output "Azure SQL firewall rule removed."
Write-Output "Server: $($server.fullyQualifiedDomainName)"
Write-Output "Rule: $RuleName"
