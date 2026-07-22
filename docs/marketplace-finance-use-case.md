# Marketplace Finance Use Case

## Purpose

ECloe is best positioned as a next-best-action engine for an integrated marketplace and digital wallet ecosystem. The practical scenario is built around two simulated product surfaces:

- **ECloe Market** - a marketplace app that produces commerce intent signals.
- **ECloe Pay** - a digital wallet and payment account that exposes eligible financial actions.
- **ECloe Engine** - the adaptive decision layer that chooses the next best eligible action.

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

## Product Roles

| Product surface | Role in the MVP | Example signals or actions |
|:---|:---|:---|
| ECloe Market | Simulates shopping behavior and purchase intent | Category visits, cart events, checkout recurrence, purchase habit |
| ECloe Pay | Simulates wallet context and eligible financial actions | Cashback eligibility, savings goal, account benefit, installment education |
| ECloe Engine | Selects the next best eligible action | Baseline, Epsilon-Greedy, UCB, Thompson Sampling |

This separation keeps the demo concrete without pretending to run a full bank, credit bureau, or regulated payment institution.

## Minimized Context

Production-like features should be aggregated and non-sensitive:

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
  ]
}
```

The implemented local API intentionally accepts only these minimized serving fields. Richer marketplace, wallet, and eligibility signals remain upstream responsibilities until they are explicitly mapped into a validated model artifact.

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

This mapping lets the team validate policy behavior safely before any real ECloe Market or ECloe Pay event stream is used.

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
