# Runbook

## Readiness Failure

1. Check Container Apps revision logs.
2. Confirm `ARTIFACT_SOURCE=azure_blob`.
3. Confirm `promoted/current.json` exists in the artifact container.
4. Run `python -m src.evaluation.validate_artifacts` locally against the candidate artifacts.
5. Confirm the runtime identity has Storage Blob Data Reader and Cosmos DB Built-in Data Contributor access.

## Artifact Rollback

1. Identify the last valid `run_id`.
2. Update `promoted/current.json` to that run's manifest path.
3. Restart the Container App revision or wait for the next cold start.
4. Verify `/readyz` and `/v1/policies/current`.
5. Run one decision and one reward smoke test with non-sensitive payloads.

## Application Rollback

Use Container Apps revision rollback or redeploy the prior image tag. Artifact rollback is separate; do not change both at once unless both the image and artifact run are known bad.

## Logs

Use Application Insights or Log Analytics to inspect:

- 5xx responses;
- p95 latency;

## Platform SLOs and alerts

The production targets are 99.5% availability, p95 Engine latency below 500 ms,
and less than 1% HTTP 5xx responses. Readiness failures alert after three
consecutive evaluation periods. The Bicep deployment creates availability,
latency, and failed-request alerts against Application Insights. Check the
`/metrics` endpoint for bounded local counters and correlate incidents with
`X-Request-Id` and `X-Trace-Id`.
- readiness failures;
- artifact loading failures;
- Cosmos DB exceptions;
- decisions and rewards grouped by artifact version.

Logs must not include bearer tokens, full customer context, salts, connection strings, Kaggle data, or raw decision payloads.
