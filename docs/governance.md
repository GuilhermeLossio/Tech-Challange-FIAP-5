# Governance - ECloe

## Purpose

This document defines governance expectations for ECloe policy releases, auditability, rollback, human review, and compliance checkpoints. It applies to the target production architecture and future implementation work.

The target product context is an integrated marketplace and digital wallet ecosystem. ECloe ranks eligible actions; it does not approve credit, define eligibility, price financial products, or make fraud decisions.

## Release Approval

A new policy version can be promoted only after:

- Offline evaluation is complete and reproducible.
- Metrics are compared against the deterministic baseline and previous approved policy.
- Fairness index is reviewed across synthetic segments.
- Reason codes are present and auditable.
- Rollback instructions are documented.
- A human approver records the release decision.

## Roles

| Role | Responsibility |
|------|----------------|
| ML Engineering | Policy implementation, metrics, evaluation, and model card updates |
| Data Engineering | Dataset processing, synthetic generation, lineage, and validation |
| Security | Secret handling, access review, logging controls, and incident response |
| DPO and legal | LGPD review, legitimate interest assessment, and privacy sign-off |
| Product owner | Business objective, acceptable experiment boundaries, and release approval |
| Eligibility owner | Marketplace, wallet, risk, and compliance rules that define eligible actions before ECloe ranks them |

## Audit Logging

Each decision log should include:

- Anonymous `session_id` or request reference.
- `decision_id`.
- Selected `offer_id`.
- `policy` and `policy_version`.
- `reason_codes`.
- Timestamp.

Logs must not include direct identifiers, sensitive attributes, income, wealth, or precise location.
Raw item-level purchase history should not be logged by ECloe; use aggregated marketplace and wallet behavior bands.

## Human Review

Human review is required for:

- Policy promotion.
- Material metric degradation.
- Fairness or exposure anomalies.
- Incident response.
- Any decision category that could create legal or similarly significant effects.

## Rollback

Rollback should restore the last approved policy version and preserve decision logs for audit. Rollback is triggered by severe latency degradation, increased error rate, fairness alerts, unexpected regret increase, data leakage findings, or privacy incidents.

## Compliance Checkpoints

| Checkpoint | Required evidence |
|------------|-------------------|
| Data processing | Data source, generation config, validation report |
| Privacy | LGPD plan alignment and minimization review |
| Eligibility boundary | Evidence that eligible actions are filtered before ECloe decisioning |
| Model release | Model card, evaluation report, approval record |
| API release | Contract tests and fallback behavior |
| Operations | Monitoring dashboard and incident response path |

## Documentation Updates

The model card, system card, LGPD plan, API contract, and evaluation plan must be reviewed whenever the policy behavior, data flow, or production assumptions change.
