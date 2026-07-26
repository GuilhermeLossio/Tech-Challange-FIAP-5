# Demo Script - ECloe

## Goal

Use this script to present ECloe as a practical ML Engineering MVP for adaptive marketplace-finance experimentation. The presentation should show a deterministic ECloe Market and ECloe Pay journey consuming the implemented ECloe Engine API, while keeping eligibility, risk, compliance, and regulated financial decisions outside the Engine.

## Short Presentation Sequence

| Step | Presenter action | Status | Presenter note |
|:---|:---|:---|:---|
| 1 | Select the recurring marketplace customer. | Planned for demo | Use a deterministic persona so the same context, eligible offers, and expected reward can be repeated. |
| 2 | Open ECloe Market. | Planned for demo | Explain that marketplace events are simulated and stay in the demo layer. |
| 3 | Add a recurring-purchase product to the cart. | Planned for demo | Point out that the raw product event is not sent directly to ECloe Engine. |
| 4 | Open checkout. | Planned for demo | Checkout is the main decision moment. |
| 5 | Show eligible offers. | Planned for demo | Eligibility occurs before recommendation; ECloe Engine ranks only eligible offers. |
| 6 | Request an ECloe decision. | Planned for demo | The planned UI calls the implemented `POST /v1/decisions` endpoint with minimized context and an `Idempotency-Key`. |
| 7 | Display the cashback recommendation. | Planned for demo | Customer-facing mode shows the benefit, not artifact checksums or raw reason codes. |
| 8 | Open the technical explanation. | Planned for demo | Technical mode may show request ID, decision ID, selected offer, policy, artifact version, and simulated likelihood. |
| 9 | Accept the offer. | Planned for demo | The UI records a verified demo interaction. |
| 10 | Register the reward. | Planned for demo | The planned UI calls the implemented `POST /v1/rewards` endpoint with `event_type=conversion` and a deterministic demo reward. |
| 11 | Open the journey summary. | Planned for demo | Show session ID, request ID, decision ID, event ID, latency, reward, and excluded sensitive fields. |
| 12 | Show the policy and artifact screen. | Planned for demo | Separate online serving strategy from offline promoted policy. |

## Presenter Notes

### Why Eligibility Occurs Before Recommendation

Eligibility, risk, compliance, and business rules decide which offers may be shown. ECloe Engine only receives the eligible offers and selects one of them. This prevents the demo from implying that ECloe approves credit, loans, limits, eligibility, fraud decisions, risk decisions, or regulated financial products.

### Why Only Minimized Context Reaches ECloe

Raw marketplace events and exact cart contents remain in the demo layer. The planned BFF aggregates them into validated context such as `channel`, `history_segment`, and `newbie` before calling ECloe Engine. This keeps the demo aligned with the current API allowlist and data-minimization boundary.

### Why Reward Registration Does Not Mean Instant Learning

`POST /v1/rewards` records an append-only reward event linked to a decision. The presenter should say that the event will be available for future policy evaluation. Do not say that the model retrains immediately or that online behavior changes instantly after the reward.

### Why Serving Policy and Offline Promoted Policy May Differ

The online serving strategy is the strategy returned by `GET /v1/policies/current` and used at request time. The offline promoted policy is the result of local policy comparison and should be reviewed as offline evidence. The demo should show both, but it must not imply that the offline promoted policy is serving online unless the implementation confirms it.

## Suggested Talk Track

1. ECloe Market simulates a marketplace checkout journey.
2. ECloe Pay simulates wallet benefits and offer interaction.
3. A planned demo BFF aggregates context and calculates eligible offers.
4. ECloe Engine receives only minimized context and eligible offers.
5. The Engine returns one selected eligible offer.
6. The customer accepts, dismisses, or opens the offer.
7. The reward event is recorded for future offline evaluation.
8. ECloe Control Room explains the technical journey, policies, artifacts, and operational status.

## Closing

ECloe demonstrates how a marketplace-finance next-best-action engine can be presented as a low-consumption ML Engineering MVP with clear eligibility boundaries, minimized data, offline evaluation, and auditable decision and reward events.

Full interface details are documented in [`demo-interface.md`](demo-interface.md).
Dedicated ECloe Pay wallet details are documented in [`ecloe-pay.md`](ecloe-pay.md).
