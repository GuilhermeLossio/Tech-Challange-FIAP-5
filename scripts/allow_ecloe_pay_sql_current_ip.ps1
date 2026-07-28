param(
    [string]$ResourceGroupName = "FIAPTechChallange5",
    [string]$ServerName = "ecloe-sql-1266",
    [string]$RuleName = "AllowCurrentClientIp"
)

$ErrorActionPreference = "Stop"

$ip = (Invoke-RestMethod -Uri "https://api.ipify.org?format=text").Trim()
if (-not $ip) {
    throw "Could not detect current public IP address."
}

az sql server update `
    --resource-group $ResourceGroupName `
    --name $ServerName `
    --enable-public-network true `
    --only-show-errors `
    --output none

az sql server firewall-rule create `
    --resource-group $ResourceGroupName `
    --server $ServerName `
    --name $RuleName `
    --start-ip-address $ip `
    --end-ip-address $ip `
    --query "{name:name,startIpAddress:startIpAddress,endIpAddress:endIpAddress}" `
    --output json `
    --only-show-errors

Write-Host "ECloe Pay Azure SQL allows only the current client IP for this rule: $ip"
