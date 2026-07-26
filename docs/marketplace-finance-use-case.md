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

The planned demo interface should simulate the full journey without implementing real financial eligibility, credit, risk, fraud, or compliance decisions.

| Step | Area | Status | Demo behavior |
|:---|:---|:---|:---|
| 1 | Demo launcher | Planned for demo | Select a deterministic persona, channel, presentation mode, technical mode, session ID, and seed. |
| 2 | ECloe Market | Planned for demo | Browse categories, view a product, add it to cart, and start checkout. |
| 3 | Context aggregation | Planned for demo | Convert raw UI events into minimized fields such as `channel`, `history_segment`, and `newbie`. |
| 4 | Eligibility simulation | Planned for demo | Produce eligible offers before ECloe Engine is called. |
| 5 | Checkout recommendation | Planned for demo | Call `POST /v1/decisions` and display one selected eligible offer. |
| 6 | Offer interaction | Planned for demo | Open, dismiss, or accept the selected offer. |
| 7 | Reward event | Planned for demo | Call the implemented `POST /v1/rewards` endpoint after a verified demo interaction. |
| 8 | ECloe Pay | Planned for demo | Show simulated wallet balance, cashback, savings goals, benefits, and accepted-offer status. |
| 9 | Journey summary | Planned for demo | Show the technical timeline with session ID, request ID, decision ID, event ID, policy, artifact version, latency, reward, and excluded fields. |
| 10 | ECloe Control Room | Planned for demo | Inspect the Decision Lab, policy/artifact separation, events, and operations status. |

### Marketplace Interface Flow

ECloe Market should show a marketplace header, categories, product cards, cart, ECloe Pay shortcut, recommendation area, and demo connection status. Possible simulated actions include viewing a category, viewing a product, adding an item to cart, removing an item, opening the cart, and starting checkout.

Raw marketplace interaction events remain in the demo layer. Raw item-level browsing history and exact cart contents must not be sent directly to ECloe Engine.

### Wallet Interface Flow

ECloe Pay should show a simulated wallet balance, cashback, savings goals, benefits, recent simulated transactions, recommended benefit, and accepted-offer status. After a reward is registered, it may state that the interaction was recorded and will be available for future policy evaluation. It must not claim immediate online learning or instant retraining.

The dedicated ECloe Pay scope, screen inventory, wallet data boundaries, reward flow, and Azure direction are documented in [`ecloe-pay.md`](ecloe-pay.md).

### Checkout Recommendation

Checkout is the main decision point. The demo layer first calculates eligible offers:

```json
{
  "eligibility_snapshot_id": "elig_demo_001",
  "eligible_offers": [
    "cashback_recurring_purchase",
    "savings_goal",
    "financial_education"
  ]
}
```

Then the planned demo BFF calls the implemented ECloe Engine decision endpoint:

```http
POST /v1/decisions
Idempotency-Key: demo-session:checkout:interaction
```

ECloe Engine chooses one eligible offer from the request. It does not invent eligibility and does not approve regulated financial products.

### Offer Interaction and Reward Event

| User action | Event type | Demo reward |
|:---|:---|---:|
| Open offer | `click` | `0.2` |
| Dismiss offer | `dismissal` | `0.0` |
| Accept offer | `conversion` | `1.0` |

These values are acceptable only for the deterministic demo. In a real integration, trusted backend services must map verified business events to configured reward values.

### Control Room

ECloe Control Room is a technical and operational interface for demonstration judges, developers, and evaluators. It should include:

- Decision Lab for request/response examples.
- Policy and artifacts screen separating online serving strategy from offline promoted policy.
- Decisions and rewards screen dependent on future administrative read endpoints.
- Operations screen connected to existing liveness, readiness, and telemetry signals where available.

The demo should show the product value: adaptive personalization across commerce and wallet channels with low operational cost and clear governance.

See [`demo-interface.md`](demo-interface.md) for the full planned screen inventory, states, API calls, and status labels. See [`ecloe-pay.md`](ecloe-pay.md) for the dedicated wallet surface documentation.
