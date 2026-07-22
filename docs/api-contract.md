# API Contract - ECloe Decision Service

## Scope

This document defines the local Decision API payloads for ECloe. The target use case is an integrated marketplace and digital wallet channel where **ECloe Market** provides commerce behavior signals, **ECloe Pay** provides wallet context and eligible actions, and **ECloe Engine** selects the next best action. The MVP exposes these contracts through FastAPI and keeps reward storage as a future integration.

## Implemented Endpoints

| Method | Path | Required scope | Description |
|:---|:---|:---|:---|
| `GET` | `/livez` | None | Returns liveness for the HTTP process. |
| `GET` | `/readyz` | None | Returns readiness after serving artifacts are loaded. |
| `GET` | `/v1/policies/current` | `policy:read` | Returns the serving strategy, serving artifact metadata, and promoted offline policy metadata. |
| `POST` | `/v1/likelihood-estimates` | `decision:read` | Estimates purchase or conversion probability for eligible offers. |
| `POST` | `/v1/purchase-likelihood` | `decision:read` | Deprecated alias for `/v1/likelihood-estimates`. |
| `POST` | `/v1/decisions` | `decision:write` | Selects one eligible offer and returns likelihood, policy, and reason codes. |
| `POST` | `/v1/rewards` | `reward:write` | Appends a reward event for an existing decision. |

Cloud runtime uses Microsoft Entra ID bearer tokens. Business routes reject requests without a valid token and required scope. Local development may set `AUTH_MODE=disabled` only when the API binds to `127.0.0.1`.

Available scopes:

- `decision:read` - read likelihood estimates.
- `decision:write` - create decisions.
- `reward:write` - write future reward events.
- `policy:read` - read active policy metadata.

`POST /v1/decisions` accepts the optional `Idempotency-Key` header, up to 128 characters. Repeating a decision request with the same authenticated subject and the same `Idempotency-Key` returns the original persisted decision response and does not create a second decision event.

## Decision Request

```json
{
  "customer_context": {
    "channel": "Web",
    "history_segment": "2) $100 - $200",
    "newbie": 1
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
| `request_id` | string | Yes | Client-generated request identifier, 1 to 64 characters |
| `customer_context.channel` | enum | Yes | One of `Web`, `Phone`, or `Multichannel` |
| `customer_context.history_segment` | string | No | Coarse Hillstrom history segment used by the likelihood artifact |
| `customer_context.newbie` | enum | No | `0` or `1` indicator used by the likelihood artifact |
| `eligible_offers` | array of enums | Yes | One to ten unique eligible offers already approved by upstream marketplace, wallet, risk, and compliance rules |

The API uses an allowlist for `customer_context`. Unknown context fields, unknown offers, duplicate offers, oversized request identifiers, and invalid enum values are rejected.

## Decision Response

```json
{
  "decision_id": "dec_123",
  "created_at": "2026-07-22T12:00:00Z",
  "offer_id": "cashback_recurring_purchase",
  "purchase_likelihood": 0.1375,
  "policy": "likelihood_ranker",
  "policy_version": "likelihood-v1",
  "artifact_schema": "purchase_likelihood_model.v1",
  "artifact_version": "likelihood-v1",
  "artifact_checksum": "64-character-sha256-checksum",
  "artifact_status": "active",
  "reason_codes": ["highest_validated_purchase_likelihood", "contextual_conversion_rate"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `decision_id` | string | Identifier used to connect later rewards to the decision |
| `created_at` | string | UTC timestamp generated when the persisted decision is created |
| `offer_id` | string | Selected eligible action from `eligible_offers` |
| `purchase_likelihood` | number | Offline estimated probability of purchase or conversion for the selected offer |
| `policy` | string | Strategy actually executed to make the decision |
| `policy_version` | string | Version of the executed strategy artifact or configuration |
| `artifact_schema` | string | Schema contract validated for the artifact used by the executed strategy |
| `artifact_version` | string | Version of the artifact used by the executed strategy |
| `artifact_checksum` | string | SHA-256 checksum of the artifact used by the executed strategy |
| `artifact_status` | string | Runtime validation status of the artifact used by the executed strategy |
| `reason_codes` | array of strings | Auditable explanation codes |

The local serving strategy is currently `likelihood_ranker`, which ranks eligible offers by the purchase-likelihood artifact. The API must not return `thompson_sampling` unless a Thompson Sampling strategy actually selects the offer at request time.

## Purchase Likelihood Response

```json
{
  "request_id": "req_123",
  "estimates": [
    {
      "offer_id": "cashback_recurring_purchase",
      "proxy_action": "womens_email",
      "purchase_likelihood": 0.1375,
      "confidence": "medium",
      "fallback_level": "action_rate",
      "sample_count": 1200,
      "reason_codes": ["action_conversion_rate", "context_fallback"],
      "warnings": []
    }
  ],
  "warnings": []
}
```

The probability is an offline simulated estimate derived from public proxy data. It must not be presented as proof of real customer intent.

## Reward Event

Request:

```json
{
  "decision_id": "dec_123",
  "event_id": "evt_123",
  "event_type": "conversion",
  "reward": 1.0,
  "occurred_at": "2026-07-05T15:00:00Z"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision_id` | string | Yes | Decision identifier returned by the Decision API |
| `event_id` | string | Yes | Client event identifier used as the reward idempotency key |
| `event_type` | string | Yes | Event such as `click`, `conversion`, or `dismissal` |
| `reward` | number | Yes | Numeric reward signal from `0.0` to `1.0` |
| `occurred_at` | string | Yes | ISO 8601 timestamp for the event; must not be earlier than the decision timestamp |

Response:

```json
{
  "decision_id": "dec_123",
  "event_id": "evt_123",
  "event_type": "conversion",
  "reward": 1.0,
  "occurred_at": "2026-07-05T15:00:00+00:00",
  "accepted": true
}
```

Reward ingestion is append-only. The decision must exist for the authenticated `subject_key`, and `event_id` is idempotent for that subject. Repeating the same `event_id` returns the original reward response without creating a duplicate event. Unknown decisions, timestamps earlier than the decision, invalid reward values, and decisions owned by another subject are rejected.

## Error Conventions

Implemented routes return structured errors for:

- Missing required fields.
- Empty `eligible_offers`.
- Unknown offer identifiers.
- Unsupported channel or segment values.
- Unknown context fields.
- Duplicate offers.
- Reward events for unknown `decision_id` values.
- Service unavailable or fallback activation.

Error payloads include a machine-readable `code` and a human-readable `message`.

## Privacy Constraints

Payloads must not include direct identifiers, sensitive attributes, income, wealth, precise location, or raw browsing data. Upstream systems are responsible for eligibility filtering before calling the Decision API.

Raw item-level purchase history should be transformed into coarse features before reaching ECloe. Examples include `frequent_grocery`, `high_value_cart`, or `recurring_checkout`, not full basket contents.
