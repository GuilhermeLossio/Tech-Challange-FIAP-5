# API Contract - ECloe Decision Service

## Scope

This document defines the planned Decision API payloads for ECloe. The target use case is an integrated marketplace and digital wallet channel where **ECloe Market** provides commerce behavior signals, **ECloe Pay** provides wallet context and eligible actions, and **ECloe Engine** selects the next best action. The MVP can start with a local script or notebook, but any future API should preserve this request, response, and reward shape.

## Decision Request

```json
{
  "customer_context": {
    "marketplace_segment": "recurring_buyer",
    "purchase_habit": "frequent_grocery",
    "wallet_engagement": "high",
    "channel": "mobile_app",
    "risk_band": "eligible_low_risk"
  },
  "eligible_offers": [
    "cashback_recurring_purchase",
    "savings_goal",
    "financial_education"
  ],
  "request_id": "req_123"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request_id` | string | Yes | Client-generated request identifier |
| `customer_context.marketplace_segment` | string | Yes | Synthetic or anonymized marketplace behavior segment |
| `customer_context.purchase_habit` | string | Yes | Coarse purchase habit such as recurring category or checkout pattern |
| `customer_context.wallet_engagement` | string | Yes | Coarse digital wallet engagement band |
| `customer_context.channel` | string | Yes | Channel such as `mobile_app`, `checkout`, or `crm` |
| `customer_context.risk_band` | string | Yes | Coarse eligibility context provided by upstream rules |
| `eligible_offers` | array of strings | Yes | Actions already approved by marketplace, wallet, risk, and compliance rules |

## Decision Response

```json
{
  "decision_id": "dec_123",
  "offer_id": "cashback_recurring_purchase",
  "policy": "thompson_sampling",
  "policy_version": "2026-07-05.1",
  "reason_codes": ["marketplace_behavior_match", "wallet_engagement_signal"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `decision_id` | string | Identifier used to connect later rewards to the decision |
| `offer_id` | string | Selected eligible action from `eligible_offers` |
| `policy` | string | Policy used to make the decision |
| `policy_version` | string | Version of the policy artifact or configuration |
| `reason_codes` | array of strings | Auditable explanation codes |

## Reward Event

```json
{
  "decision_id": "dec_123",
  "event_type": "conversion",
  "reward": 1.0,
  "occurred_at": "2026-07-05T15:00:00Z"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision_id` | string | Yes | Decision identifier returned by the Decision API |
| `event_type` | string | Yes | Event such as `click`, `conversion`, or `dismissal` |
| `reward` | number | Yes | Numeric reward signal, usually `0.0` or `1.0` |
| `occurred_at` | string | Yes | ISO 8601 timestamp for the event |

## Error Conventions

Future implementations should return structured errors for:

- Missing required fields.
- Empty `eligible_offers`.
- Unknown offer identifiers.
- Unsupported channel or segment values.
- Reward events for unknown `decision_id` values.
- Service unavailable or fallback activation.

Error payloads should include a machine-readable code, a human-readable message, and the original `request_id` when available.

## Privacy Constraints

Payloads must not include direct identifiers, sensitive attributes, income, wealth, precise location, or raw browsing data. Upstream systems are responsible for eligibility filtering before calling the Decision API.

Raw item-level purchase history should be transformed into coarse features before reaching ECloe. Examples include `frequent_grocery`, `high_value_cart`, or `recurring_checkout`, not full basket contents.
