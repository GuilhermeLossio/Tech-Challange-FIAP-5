# Marketplace Finance Use Case

## Purpose

ECloe is best positioned as a next-best-action engine for an integrated marketplace and digital wallet ecosystem. The practical scenario is similar to a marketplace app connected to a payment account: marketplace behavior creates intent signals, and the digital wallet exposes eligible financial actions.

The MVP does not decide credit, eligibility, fraud, or account restrictions. It chooses which already eligible action should be presented first in a digital channel.

## Real-World Scenario

```text
Marketplace behavior
  purchases, categories, cart, checkout, recurrence
        ↓
Digital wallet context
  payment method, cashback, account engagement, eligible actions
        ↓
ECloe decision engine
  next best eligible action
        ↓
Digital channel
  app banner, checkout message, CRM card, push notification
        ↓
Reward event
  click, ignore, accept, conversion
```

## Example Actions

| Marketplace or wallet signal | Eligible financial action |
|:---|:---|
| Frequent grocery purchases | Cashback offer for recurring purchases |
| High-value cart abandonment | Installment education or wallet benefit |
| Repeated installment usage | Financial education content |
| Idle wallet balance | Savings goal or simple investment offer |
| High app engagement | Account upgrade or premium benefit |
| Seasonal purchase pattern | Timed partner reward or cashback campaign |

## Minimized Context

Production-like features should be aggregated and non-sensitive:

```json
{
  "customer_context": {
    "channel": "mobile_app",
    "marketplace_segment": "recurring_buyer",
    "purchase_habit": "frequent_grocery",
    "wallet_engagement": "high",
    "relationship_recency": "recent",
    "risk_band": "eligible_low_risk"
  },
  "eligible_offers": [
    "cashback_recurring_purchase",
    "savings_goal",
    "financial_education"
  ]
}
```

Excluded fields:

- direct identity;
- raw account balance;
- exact income or wealth;
- precise location;
- sensitive attributes;
- detailed credit score;
- raw browsing or item-level purchase history.

## Dataset Mapping

The Hillstrom dataset is a public proxy for the marketplace-finance pattern:

| Hillstrom concept | Marketplace-finance interpretation |
|:---|:---|
| `segment` | Historical action or campaign shown |
| `conversion` | Click, accept, or conversion reward |
| `channel` | Digital channel or touchpoint |
| `history_segment` | Coarse prior engagement segment |
| Campaign row | One past interaction between context, action, and reward |

This mapping lets the team validate policy behavior safely before any real marketplace or wallet data is used.

## Product Boundary

ECloe works after upstream eligibility controls:

```text
Eligibility and risk rules decide what the user may receive.
ECloe decides which eligible action should be shown now.
```

This boundary keeps the MVP useful while avoiding claims that the model approves credit, prices products, or makes regulated financial decisions.

## Demo Direction

A future demo interface should simulate:

- a marketplace home or checkout area;
- a connected digital wallet panel;
- a fictional customer context;
- eligible financial actions;
- the ECloe recommendation;
- click, ignore, and accept reward buttons;
- event logging for decisions and rewards.

The demo should show the product value: adaptive personalization across commerce and wallet channels with low operational cost and clear governance.
