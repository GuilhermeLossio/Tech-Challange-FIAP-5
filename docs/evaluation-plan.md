# Evaluation Plan - ECloe

## Purpose

This document defines how ECloe policies should be evaluated before any policy version is approved. The current repository does not contain executed experiments; the plan describes the expected evaluation process for future implementation.

## Evaluation Layers

| Layer | Goal |
|-------|------|
| Contract validation | Confirm request, response, and reward payloads match the API contract |
| Offline policy evaluation | Compare Thompson Sampling, Nilos-UCB, and deterministic baseline |
| Golden set validation | Ensure known scenarios produce expected behavior |
| Fairness review | Check exposure balance across synthetic segments |
| Operational review | Confirm latency, logging, rollback, and observability readiness |

## Primary Metrics

| Metric | Interpretation |
|--------|----------------|
| Conversion rate | Higher is better when measured on comparable synthetic cohorts |
| Cumulative regret | Lower indicates better offer selection over time |
| Exploration ratio | Must remain within the configured experiment budget |
| Reward latency | Lower improves feedback speed, but delayed rewards must remain supported |
| Fairness index | Exposure variation across synthetic segments must remain explainable |
| API latency p95 | Future serving endpoint should remain within the service target |

## Golden Set Expectations

The golden set should contain at least 20 deterministic cases covering:

- Valid requests with multiple eligible offers.
- Requests with a single eligible offer.
- Missing or invalid `customer_context` fields.
- Unknown `offer_id` values.
- Segments with low historical evidence.
- Reward events for known and unknown `decision_id` values.
- Delayed rewards after the initial decision window.
- Cases where the deterministic baseline should be selected as fallback.

Each case should include an expected pass/fail outcome and the reason for the expectation.

## Pass and Fail Criteria

A policy version passes evaluation when:

- It is reproducible from recorded configuration and data version references.
- It performs better than or equal to the deterministic baseline on the selected primary metric.
- It does not create unexplained exposure concentration across synthetic segments.
- It emits reason codes for decisions.
- It supports rollback to the previous approved version.

A policy version fails evaluation when:

- It relies on leakage fields or unavailable production-time data.
- It cannot be reproduced.
- It lacks decision logs or reason codes.
- It materially worsens regret, fairness, or operational reliability.

## Reporting Outputs

Each evaluation run should produce:

- Policy name and version.
- Dataset and synthetic generation version.
- Metric table by offer and segment.
- Fairness summary.
- Drift summary when applicable.
- Known limitations.
- Approval recommendation.

