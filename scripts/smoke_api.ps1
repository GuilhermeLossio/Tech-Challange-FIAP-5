param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$BearerToken = ""
)

$ErrorActionPreference = "Stop"

$headers = @{}
if ($BearerToken) {
    $headers["Authorization"] = "Bearer $BearerToken"
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message =="
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw "Assertion failed: $Message"
    }
    Write-Host "PASS: $Message"
}

function Invoke-Api {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [hashtable]$ExtraHeaders = @{}
    )

    $requestHeaders = @{}
    foreach ($key in $headers.Keys) {
        $requestHeaders[$key] = $headers[$key]
    }
    foreach ($key in $ExtraHeaders.Keys) {
        $requestHeaders[$key] = $ExtraHeaders[$key]
    }

    $params = @{
        Method = $Method
        Uri = "$BaseUrl$Path"
        Headers = $requestHeaders
    }

    if ($null -ne $Body) {
        $params["ContentType"] = "application/json"
        $params["Body"] = ($Body | ConvertTo-Json -Depth 12)
    }

    try {
        $payload = Invoke-RestMethod @params
        return [pscustomobject]@{
            Ok = $true
            StatusCode = 200
            Body = $payload
        }
    }
    catch {
        $statusCode = 0
        $errorBody = $null
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
            try {
                $stream = $_.Exception.Response.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($stream)
                $raw = $reader.ReadToEnd()
                if ($raw) {
                    $errorBody = $raw | ConvertFrom-Json
                }
            }
            catch {
                $errorBody = $_.Exception.Message
            }
        }

        return [pscustomobject]@{
            Ok = $false
            StatusCode = $statusCode
            Body = $errorBody
        }
    }
}

$decisionPayload = @{
    request_id = "smoke_req_001"
    customer_context = @{
        channel = "Web"
        history_segment = "1) Low"
        newbie = 1
    }
    eligible_offers = @(
        "cashback_recurring_purchase",
        "financial_education",
        "savings_goal"
    )
}

Write-Step "Liveness"
$livez = Invoke-Api -Method "GET" -Path "/livez"
Assert-True $livez.Ok "/livez returns success"
Assert-True ($livez.Body.status -eq "ok") "/livez status is ok"

Write-Step "Readiness"
$readyz = Invoke-Api -Method "GET" -Path "/readyz"
Assert-True $readyz.Ok "/readyz returns success"
Assert-True ($readyz.Body.status -eq "ready") "/readyz status is ready"

Write-Step "Current Policy"
$policy = Invoke-Api -Method "GET" -Path "/v1/policies/current"
Assert-True $policy.Ok "/v1/policies/current returns success"
Assert-True ($policy.Body.policy -eq "likelihood_ranker") "current policy is likelihood_ranker"
Assert-True ($policy.Body.artifact_checksum.Length -eq 64) "policy artifact checksum is sha256-sized"

Write-Step "Likelihood Estimates"
$likelihood = Invoke-Api -Method "POST" -Path "/v1/likelihood-estimates" -Body $decisionPayload
Assert-True $likelihood.Ok "/v1/likelihood-estimates returns success"
Assert-True ($likelihood.Body.estimates.Count -eq $decisionPayload.eligible_offers.Count) "one estimate per eligible offer"
Assert-True ($likelihood.Body.estimates[0].purchase_likelihood -ge 0) "likelihood is not negative"
Assert-True ($likelihood.Body.estimates[0].purchase_likelihood -le 1) "likelihood is not above one"

Write-Step "Deprecated Purchase Likelihood Alias"
$alias = Invoke-Api -Method "POST" -Path "/v1/purchase-likelihood" -Body $decisionPayload
Assert-True $alias.Ok "/v1/purchase-likelihood alias returns success"
Assert-True ($alias.Body.estimates.Count -eq $likelihood.Body.estimates.Count) "alias returns same number of estimates"

Write-Step "Decision Idempotency"
$decisionHeaders = @{
    "Idempotency-Key" = "smoke-idem-001"
}
$decision = Invoke-Api -Method "POST" -Path "/v1/decisions" -Body $decisionPayload -ExtraHeaders $decisionHeaders
$decisionAgain = Invoke-Api -Method "POST" -Path "/v1/decisions" -Body $decisionPayload -ExtraHeaders $decisionHeaders
Assert-True $decision.Ok "/v1/decisions returns success"
Assert-True $decisionAgain.Ok "repeated /v1/decisions returns success"
Assert-True ($decision.Body.decision_id -eq $decisionAgain.Body.decision_id) "same idempotency key returns same decision"
Assert-True ($decision.Body.offer_id -in $decisionPayload.eligible_offers) "selected offer belongs to eligible offers"
Assert-True ($decision.Body.purchase_likelihood -ge 0 -and $decision.Body.purchase_likelihood -le 1) "decision likelihood is between zero and one"

Write-Step "Reward Ingestion"
$rewardPayload = @{
    decision_id = $decision.Body.decision_id
    event_id = "smoke_evt_001"
    event_type = "conversion"
    reward = 1.0
    occurred_at = (Get-Date).ToUniversalTime().AddSeconds(5).ToString("o")
}
$reward = Invoke-Api -Method "POST" -Path "/v1/rewards" -Body $rewardPayload
$rewardAgain = Invoke-Api -Method "POST" -Path "/v1/rewards" -Body $rewardPayload
Assert-True $reward.Ok "/v1/rewards returns success"
Assert-True $rewardAgain.Ok "repeated /v1/rewards returns success"
Assert-True $reward.Body.accepted "reward is accepted"
Assert-True ($reward.Body.event_id -eq $rewardAgain.Body.event_id) "same event_id is idempotent"

Write-Step "Validation Errors"
$duplicateOffersPayload = @{
    request_id = "smoke_req_duplicate"
    customer_context = @{
        channel = "Web"
        history_segment = "1) Low"
        newbie = 1
    }
    eligible_offers = @("savings_goal", "savings_goal")
}
$duplicateOffers = Invoke-Api -Method "POST" -Path "/v1/decisions" -Body $duplicateOffersPayload
Assert-True (-not $duplicateOffers.Ok) "duplicate offers are rejected"
Assert-True ($duplicateOffers.StatusCode -eq 422) "duplicate offers return HTTP 422"

$unknownOfferPayload = @{
    request_id = "smoke_req_unknown_offer"
    customer_context = @{
        channel = "Web"
        history_segment = "1) Low"
        newbie = 1
    }
    eligible_offers = @("not_a_real_offer")
}
$unknownOffer = Invoke-Api -Method "POST" -Path "/v1/likelihood-estimates" -Body $unknownOfferPayload
Assert-True (-not $unknownOffer.Ok) "unknown offer is rejected"
Assert-True ($unknownOffer.StatusCode -eq 422) "unknown offer returns HTTP 422"

$unknownDecisionRewardPayload = @{
    decision_id = "dec_missing"
    event_id = "smoke_evt_missing_decision"
    event_type = "conversion"
    reward = 1.0
    occurred_at = (Get-Date).ToUniversalTime().AddSeconds(5).ToString("o")
}
$unknownDecisionReward = Invoke-Api -Method "POST" -Path "/v1/rewards" -Body $unknownDecisionRewardPayload
Assert-True (-not $unknownDecisionReward.Ok) "reward for unknown decision is rejected"
Assert-True ($unknownDecisionReward.StatusCode -eq 400) "unknown decision reward returns HTTP 400"

Write-Host ""
Write-Host "All API smoke tests passed against $BaseUrl"
