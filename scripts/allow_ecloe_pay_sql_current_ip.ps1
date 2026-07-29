param(
    [string]$ResourceGroupName = "FIAPTechChallange5",
    [string]$ServerName = "ecloe-sql-1266",
    [string]$RuleName = "AllowCurrentClientIp",
    [switch]$EnablePublicNetworkAccess
)

$ErrorActionPreference = "Stop"

$script = Join-Path $PSScriptRoot "allow_current_sql_client_ip.ps1"
& $script @PSBoundParameters
