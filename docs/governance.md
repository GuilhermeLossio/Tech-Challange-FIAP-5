# Governance - ECloe

## Purpose

This document defines governance expectations for ECloe policy releases, auditability, rollback, human review, and compliance checkpoints. It applies to the target production architecture and future implementation work.

The target product context is an integrated marketplace and digital wallet ecosystem: ECloe Market produces behavior signals, ECloe Pay provides eligible actions, and ECloe Engine ranks those actions. ECloe does not approve credit, define eligibility, price financial products, or make fraud decisions.

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

- Pseudonymized `subject_key`.
- `decision_id`.
- `request_id`.
- Selected `offer_id`.
- `policy` and `policy_version`.
- Artifact version and checksum.
- `reason_codes`.
- Timestamp.
- Optional `Idempotency-Key` for duplicate suppression.
- Minimized context accepted by the serving schema.

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

## Recommendation Policy Governance

| Requirement | Status | Evidence |
|:---|:---|:---|
| Baseline is independently configurable for Market and Pay | Implemented | `RECOMMENDATION_MARKET_POLICY`, `RECOMMENDATION_PAY_POLICY` |
| Minimum evidence guardrail | Implemented | Runtime prevents likelihood promotion below 1,000 decisions or 100 positives |
| Shadow adaptive challengers | Implemented | Rankings are recorded without affecting presentation |
| Manual artifact approval record | Planned for demo | `policy_versions` and Blob promotion metadata |
| Adaptive canary | Future | Maximum epsilon 0.05 after approval |

Rollback changes only the affected surface policy or artifact pointer and preserves historical decisions. A blocked-field finding, eligibility violation, out-of-stock selection, artifact mismatch, or material objective regression triggers immediate fallback to the deterministic baseline. Full procedures are in [`recommendation-system.md`](recommendation-system.md).
