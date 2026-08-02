param(
    [string]$ResourceGroupName = "FIAPTechChallange5",
    [string]$ServerName = "ecloe-sql-1266",
    [string]$RuleName = "AllowCurrentClientIp",
    [string]$IpLookupUri = "https://api64.ipify.org?format=text",
    [switch]$EnablePublicNetworkAccess
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

function Test-StrictIpAddress {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ($Value -match "\s" -or $Value.Contains(",")) {
        return $false
    }

    $octet = "(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
    if ($Value -match "^$octet\.$octet\.$octet\.$octet$") {
        return $true
    }

    $parsed = [System.Net.IPAddress]::None
    if (-not [System.Net.IPAddress]::TryParse($Value, [ref]$parsed)) {
        return $false
    }

    return $parsed.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetworkV6
}

function Get-CurrentPublicIp {
    $response = Invoke-RestMethod -Uri $IpLookupUri
    $ip = ([string]$response).Trim()

    if ([string]::IsNullOrWhiteSpace($ip)) {
        throw "Could not detect current public IP address."
    }
    if (-not (Test-StrictIpAddress -Value $ip)) {
        throw "Public IP lookup returned an invalid or non-single IP value: '$ip'."
    }
    if ($ip -eq "0.0.0.0" -or $ip -eq "::") {
        throw "Refusing to create an Azure SQL firewall rule for '$ip'."
    }

    $parsed = [System.Net.IPAddress]::Parse($ip)
    if ([System.Net.IPAddress]::IsLoopback($parsed)) {
        throw "Public IP lookup returned a loopback address: '$ip'."
    }

    return $ip
}

function Get-TargetSqlServer {
    $servers = @(Invoke-AzJson -Arguments @(
        "sql",
        "server",
        "list",
        "--query",
        "[?name=='$ServerName'].{name:name,resourceGroup:resourceGroup,fullyQualifiedDomainName:fullyQualifiedDomainName,publicNetworkAccess:publicNetworkAccess}"
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

$ip = Get-CurrentPublicIp
$server = Get-TargetSqlServer

if ($server.publicNetworkAccess -eq "Disabled") {
    if (-not $EnablePublicNetworkAccess) {
        throw "Public network access is Disabled for '$ServerName'. Re-run with -EnablePublicNetworkAccess if local development access is required."
    }

    Write-Host "Public network access is Disabled for '$ServerName'."
    $confirmation = Read-Host "Type ENABLE to change publicNetworkAccess to Enabled"
    if ($confirmation -cne "ENABLE") {
        throw "Aborted. publicNetworkAccess was not changed."
    }

    Invoke-AzNone -Arguments @(
        "sql",
        "server",
        "update",
        "--resource-group",
        $ResourceGroupName,
        "--name",
        $ServerName,
        "--enable-public-network",
        "true"
    )
}

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
    $rule = Invoke-AzJson -Arguments @(
        "sql",
        "server",
        "firewall-rule",
        "create",
        "--resource-group",
        $ResourceGroupName,
        "--server",
        $ServerName,
        "--name",
        $RuleName,
        "--start-ip-address",
        $ip,
        "--end-ip-address",
        $ip,
        "--query",
        "{name:name,startIpAddress:startIpAddress,endIpAddress:endIpAddress}"
    )
}
else {
    $rule = Invoke-AzJson -Arguments @(
        "sql",
        "server",
        "firewall-rule",
        "update",
        "--resource-group",
        $ResourceGroupName,
        "--server",
        $ServerName,
        "--name",
        $RuleName,
        "--start-ip-address",
        $ip,
        "--end-ip-address",
        $ip,
        "--query",
        "{name:name,startIpAddress:startIpAddress,endIpAddress:endIpAddress}"
    )
}

Write-Output "Azure SQL firewall rule is ready."
Write-Output "Server: $($server.fullyQualifiedDomainName)"
Write-Output "Rule: $($rule.name)"
Write-Output "Start IP: $($rule.startIpAddress)"
Write-Output "End IP: $($rule.endIpAddress)"
Write-Output "Remove rule after development:"
Write-Output ".\scripts\remove_current_sql_client_ip.ps1 -ResourceGroupName $ResourceGroupName -ServerName $ServerName -RuleName $RuleName"
