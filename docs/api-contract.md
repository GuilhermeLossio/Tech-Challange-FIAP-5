# API Contract - ECloe Decision Service

## Scope

This document defines the planned Decision API payloads for ECloe. The MVP can start with a local script or notebook, but any future API should preserve this request, response, and reward shape.

## Decision Request

```json
{
  "customer_context": {
    "segment": "digital_high_engagement",
    "channel": "web",
    "risk_band": "low"
  },
  "eligible_offers": ["credit_limit", "personal_loan", "cashback_investment"],
  "request_id": "req_123"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request_id` | string | Yes | Client-generated request identifier |
| `customer_context.segment` | string | Yes | Synthetic or anonymized segment |
| `customer_context.channel` | string | Yes | Channel such as `web`, `app`, or `crm` |
| `customer_context.risk_band` | string | Yes | Coarse eligibility context provided by upstream rules |
| `eligible_offers` | array of strings | Yes | Offers already approved by external eligibility rules |

## Decision Response

```json
{
  "decision_id": "dec_123",
  "offer_id": "cashback_investment",
  "policy": "thompson_sampling",
  "policy_version": "2026-07-05.1",
  "reason_codes": ["segment_performance", "exploration_budget"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `decision_id` | string | Identifier used to connect later rewards to the decision |
| `offer_id` | string | Selected offer from `eligible_offers` |
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
