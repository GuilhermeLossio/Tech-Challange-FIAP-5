param(
    [string]$ResourceGroup = "FIAPTechChallange5",
    [string]$AcrName = "ecloedemo1266",
    [string]$ContainerAppsEnvironment = "ecloe-demo-aca-env",
    [string]$ContainerAppName = "ecloe-demo-web",
    [string]$IdentityName = "ecloe-demo-acr-pull",
    [string]$Location = "chilecentral",
    [string]$ImageTag = "",
    [string]$DemoPassword = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

function Invoke-AzureCli {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & az @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed with exit code $LASTEXITCODE."
    }
}

function New-RandomText {
    param([int]$Length = 32)
    $alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = [byte[]]::new($Length)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

Invoke-AzureCli account show --output none
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repositoryRoot
try {
    if (-not $ImageTag) {
        $ImageTag = (git rev-parse --short=12 HEAD).Trim()
    }
    if ($ImageTag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
        throw "ImageTag contains unsupported characters."
    }
    if (-not $DemoPassword) {
        $DemoPassword = New-RandomText -Length 24
    }
    if ($DemoPassword.Length -lt 12 -or $DemoPassword.Length -gt 128) {
        throw "DemoPassword must contain between 12 and 128 characters."
    }

    Invoke-AzureCli acr config authentication-as-arm update --registry $AcrName --status enabled --output none
    $acrLoginServer = (Invoke-AzureCli acr show --resource-group $ResourceGroup --name $AcrName `
        --query loginServer --output tsv).Trim()
    $acrId = (Invoke-AzureCli acr show --resource-group $ResourceGroup --name $AcrName --query id --output tsv).Trim()
    $environmentId = (Invoke-AzureCli containerapp env list --resource-group $ResourceGroup `
        --query "[?name=='$ContainerAppsEnvironment'].id | [0]" --output tsv | Out-String).Trim()
    if (-not $environmentId) {
        Invoke-AzureCli containerapp env create --resource-group $ResourceGroup --name $ContainerAppsEnvironment `
            --location $Location --output none
    }

    $identityId = (Invoke-AzureCli identity list --resource-group $ResourceGroup `
        --query "[?name=='$IdentityName'].id | [0]" --output tsv | Out-String).Trim()
    if (-not $identityId) {
        $identityId = (Invoke-AzureCli identity create --resource-group $ResourceGroup --name $IdentityName `
            --location $Location --query id --output tsv).Trim()
    }
    $principalId = (Invoke-AzureCli identity show --resource-group $ResourceGroup --name $IdentityName `
        --query principalId --output tsv).Trim()
    $acrPullAssignments = (Invoke-AzureCli role assignment list --assignee-object-id $principalId `
        --scope $acrId --role AcrPull --query "[].id" --output tsv | Out-String).Trim()
    if (-not $acrPullAssignments) {
        Invoke-AzureCli role assignment create --assignee-object-id $principalId `
            --assignee-principal-type ServicePrincipal --scope $acrId --role AcrPull --output none
    }

    $gitSha = (git rev-parse HEAD).Trim()
    $repository = "ecloe-demo-web"
    $image = "${acrLoginServer}/${repository}:${ImageTag}"
    if (-not $SkipBuild) {
        $buildContext = Join-Path ([System.IO.Path]::GetTempPath()) ("ecloe-build-" + [System.IO.Path]::GetRandomFileName())
        $buildArchive = "${buildContext}.zip"
        New-Item -ItemType Directory -Path $buildContext | Out-Null
        try {
            & git archive --format=zip --output=$buildArchive HEAD
            if ($LASTEXITCODE -ne 0) { throw "Could not create the clean Git build context." }
            Expand-Archive -LiteralPath $buildArchive -DestinationPath $buildContext
            Invoke-AzureCli acr build --registry $AcrName --image "${repository}:${ImageTag}" `
                --file Dockerfile.demo --build-arg "VCS_REF=${gitSha}" --build-arg "VERSION=${ImageTag}" $buildContext
        }
        finally {
            if (Test-Path -LiteralPath $buildArchive) { Remove-Item -LiteralPath $buildArchive -Force }
            if (Test-Path -LiteralPath $buildContext) { Remove-Item -LiteralPath $buildContext -Recurse -Force }
        }
    }
    else {
        $tagExists = (Invoke-AzureCli acr repository show --name $AcrName --image "${repository}:${ImageTag}" `
            --query name --output tsv | Out-String).Trim()
        if (-not $tagExists) { throw "Image not found in ACR: ${image}" }
    }

    $flaskSecret = New-RandomText -Length 64
    $subjectSalt = New-RandomText -Length 48
    $secrets = @(
        "flask-secret-key=${flaskSecret}",
        "subject-key-salt=${subjectSalt}",
        "demo-user-password=${DemoPassword}"
    )
    $envVars = @(
        "APP_ENVIRONMENT=demo",
        "ECLOE_WEB_AUTH_MODE=local",
        "ECLOE_PAY_DATABASE_MODE=memory",
        "ECLOE_MARKET_DATABASE_MODE=memory",
        "ECLOE_MARKET_CATALOG_PATH=data/demo/ecloe_market_catalog.azure.json",
        "ECLOE_PAY_COOKIE_SECURE=true",
        "FLASK_SECRET_KEY=secretref:flask-secret-key",
        "SUBJECT_KEY_SALT=secretref:subject-key-salt",
        "ECLOE_PAY_DEMO_USER_PASSWORD=secretref:demo-user-password"
    )

    $appId = (Invoke-AzureCli containerapp list --resource-group $ResourceGroup `
        --query "[?name=='$ContainerAppName'].id | [0]" --output tsv | Out-String).Trim()
    if (-not $appId) {
        $createArguments = @(
            "containerapp", "create", "--resource-group", $ResourceGroup, "--name", $ContainerAppName,
            "--environment", $ContainerAppsEnvironment, "--image", $image, "--ingress", "external",
            "--target-port", "8000", "--min-replicas", "1", "--max-replicas", "1",
            "--cpu", "0.5", "--memory", "1.0Gi", "--user-assigned", $identityId,
            "--registry-server", $acrLoginServer, "--registry-identity", $identityId, "--secrets"
        ) + $secrets + @("--env-vars") + $envVars + @("--output", "none")
        Invoke-AzureCli @createArguments
    }
    else {
        $secretArguments = @(
            "containerapp", "secret", "set", "--resource-group", $ResourceGroup,
            "--name", $ContainerAppName, "--secrets"
        ) + $secrets + @("--output", "none")
        Invoke-AzureCli @secretArguments
        Invoke-AzureCli containerapp registry set --resource-group $ResourceGroup --name $ContainerAppName `
            --server $acrLoginServer --identity $identityId --output none
        $updateArguments = @(
            "containerapp", "update", "--resource-group", $ResourceGroup, "--name", $ContainerAppName,
            "--image", $image, "--set-env-vars"
        ) + $envVars + @("--min-replicas", "1", "--max-replicas", "1", "--output", "none")
        Invoke-AzureCli @updateArguments
    }

    $fqdn = (Invoke-AzureCli containerapp show --resource-group $ResourceGroup --name $ContainerAppName `
        --query properties.configuration.ingress.fqdn --output tsv).Trim()
    $baseUrl = "https://${fqdn}"
    $healthy = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            if ((Invoke-WebRequest "${baseUrl}/healthz" -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200) {
                $healthy = $true
                break
            }
        }
        catch { Start-Sleep -Seconds 5 }
    }
    if (-not $healthy) {
        Invoke-AzureCli containerapp revision list --resource-group $ResourceGroup --name $ContainerAppName --output table
        throw "Container App did not become healthy: ${baseUrl}/healthz"
    }
    foreach ($path in @("/market", "/pay/login")) {
        $status = (Invoke-WebRequest "${baseUrl}${path}" -UseBasicParsing -TimeoutSec 15).StatusCode
        if ($status -ne 200) { throw "Smoke test failed for ${path}: HTTP ${status}" }
    }

    Write-Host "Deployment completed."
    Write-Host "URL: ${baseUrl}"
    Write-Host "Demo email: demo.market@ecloe.local"
    Write-Host "Demo password: ${DemoPassword}"
    Write-Host "Image: ${image}"
}
finally {
    Pop-Location
}
