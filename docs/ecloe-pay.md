# ECloe Pay - Digital Wallet Surface

## Status

| Area | Status | Notes |
|:---|:---|:---|
| ECloe Pay product surface | Planned for demo | Simulated wallet experience inside the ECloe Demo application. |
| Wallet summary and benefits UI | Implemented | First static demo slice in `src/demo/ecloe_pay/` shows demo balance, cashback, goals, benefits, and accepted-offer status. |
| Offer interaction flow | Implemented | First static demo slice opens, accepts, dismisses, and records deterministic reward-event evidence. |
| Terms of service and demo disclaimer | Implemented | The static demo requires explicit acceptance that no real money is processed and no real user is created. |
| Simulated authentication | Implemented | Azure SQL mode protects the Pay wallet and APIs with a demo persona, HttpOnly token cookie, CSRF checks, logout revocation, and login attempt limits. |
| Azure SQL Pay schema | Implemented | `src/demo/ecloe_pay/schema.sql` defines Pay-owned Azure SQL tables under the `ecloe_pay` schema. |
| Real-ready Azure SQL account model | Planned for demo | Next implementation step separates identity, wallet, payments, rewards, audit, and integration schemas inside `ecloe_validation`. |
| Reward registration | Implemented | Uses the existing `POST /v1/rewards` endpoint after a verified demo interaction. |
| Real payment account integration | Future | Requires governed upstream wallet, identity, security, compliance, and consent controls. |
| Credit, fraud, risk, compliance, and eligibility decisions | Out of scope | These decisions remain upstream and are not performed by ECloe Pay or ECloe Engine. |

## Purpose

ECloe Pay is the planned digital wallet surface for the ECloe demo. It turns the recommendation returned by ECloe Engine into a customer-facing wallet benefit, then records the customer interaction as an append-only reward event.

In the MVP, ECloe Pay is not a real wallet, bank account, credit product, payment processor, or risk system. It is a simulated experience that demonstrates how wallet context and marketplace behavior can support responsible next-best-action personalization after upstream systems have already decided which offers are eligible.

The first implemented demo slice is available in [`../src/demo/ecloe_pay/`](../src/demo/ecloe_pay/). It is a runnable Flask frontend/API that can also be opened as a static fallback presentation. The static fallback is explicitly labeled `Presentation mode — data is not being persisted.` and must not imply that login, terms, or payment state was persisted in Azure SQL. It includes demo-persona authentication, mandatory demo terms, deterministic simulated-payment confirmation, transaction idempotency evidence, technical mode, and optional Azure SQL persistence for Pay-owned state.

The Flask root route now serves the ECloe Pay landing page, while the runnable wallet demo is available at `/pay`.

## Architecture Diagrams

### Overview

![ECloe Pay overview](ecloe-pay-overview.svg)

The overview shows the planned ECloe Pay path from the customer-facing demo web app through the BFF, Pay API, Engine API, outbox worker, and low-consumption Azure services.

### Transfer Flow

![ECloe Pay transfer flow](ecloe-pay-transfer-flow.svg)

The transfer flow represents a planned wallet benefit interaction. It uses transactional Pay API persistence and asynchronous event publication before reward evidence reaches the Engine and event stores. It is not real payment processing.

### Simplified Relationship

![ECloe Pay simplified relationship](ecloe-pay-simplified-relationship.svg)

The simplified relationship diagram separates the customer experience layer, service layer, and state/event layer while preserving the boundary that eligibility remains upstream.

## Product Role

```text
ECloe Market checkout
    -> eligible offers
    -> ECloe Engine decision
    -> ECloe Pay benefit interaction
    -> reward event
    -> future offline evaluation
```

ECloe Pay receives the selected eligible offer from the demo session, presents it as a wallet benefit, and records whether the simulated user opened, dismissed, or accepted it. The reward event is linked to the original `decision_id` returned by ECloe Engine.

## Scope Boundaries

| Responsibility | Owner | Status | Notes |
|:---|:---|:---|:---|
| Wallet UI presentation | ECloe Pay | Planned for demo | Displays simulated wallet balance, benefits, goals, and accepted-offer state. |
| Session state | Demo Backend-for-Frontend | Planned for demo | Keeps persona, cart, decision, reward, and technical timeline state. |
| Eligibility calculation | Upstream eligibility simulator | Planned for demo | Produces allowed `eligible_offers` before calling ECloe Engine. |
| Offer ranking | ECloe Engine | Implemented | Selects one action from the eligible offers sent in the request. |
| Reward ingestion | ECloe Engine | Implemented | Persists append-only reward events through `POST /v1/rewards`. |
| Real account, credit, fraud, risk, compliance decisions | Upstream governed systems | Out of scope | Must not be simulated as Engine or Pay responsibilities. |

## Planned Screens

| Screen | Route | Status | Purpose | Engine dependency |
|:---|:---|:---|:---|:---|
| Wallet home | `/pay` | Planned for demo | Show simulated balance, cashback, goals, recent activity, and active benefit. | Uses prior decision stored in demo session. |
| Benefit details | `/pay/benefits/{offer_id}` | Planned for demo | Explain the selected eligible benefit and allow user action. | Uses `decision_id` from `POST /v1/decisions`. |
| Offer accepted state | `/pay/accepted` | Planned for demo | Confirm the simulated acceptance and reward status. | Calls `POST /v1/rewards`. |
| Wallet empty state | `/pay` | Planned for demo | Show wallet without an accepted recommendation. | No Engine call required. |
| Wallet technical drawer | Inside Pay screens | Planned for demo | Show request ID, decision ID, event ID, policy, artifact, and reward only in technical mode. | Reads session state and Engine responses. |

## Customer-Facing Content

ECloe Pay should use plain wallet language and avoid internal model terminology in customer-facing mode.

| Offer ID | Customer-facing benefit | Allowed message |
|:---|:---|:---|
| `cashback_recurring_purchase` | Cashback for recurring purchases | "Earn cashback on your recurring purchases." |
| `savings_goal` | Savings goal | "Create a goal for your next purchase." |
| `financial_education` | Financial education | "See a short guide before choosing your next benefit." |
| `installment_education` | Installment guidance | "Understand installment options before checkout." |
| `premium_benefit` | Premium wallet benefit | "Review an account benefit available for your wallet profile." |

Customer-facing mode must not display artifact checksums, raw reason codes, proxy campaign names, model internals, hidden eligibility rules, or internal request payloads.

## Technical Mode

Technical mode is for judges, developers, and reviewers. It may show:

- session ID;
- request ID;
- decision ID;
- selected `offer_id`;
- eligible offers considered;
- serving policy;
- policy version;
- artifact version and status;
- simulated purchase likelihood;
- event ID;
- event type;
- reward value;
- request latency;
- fields excluded before calling ECloe Engine.

Any probability shown in ECloe Pay must be labeled as a simulated estimate based on public proxy data, not a real prediction of customer financial behavior.

## Data Contract

ECloe Pay may display simulated wallet state locally, but only minimized context and eligible offers can reach ECloe Engine.

| Data class | ECloe Pay display? | Sent to ECloe Engine? | Status | Notes |
|:---|:---|:---|:---|:---|
| Demo balance | Yes | No | Planned for demo | Simulated local UI value only. |
| Cashback summary | Yes | No | Planned for demo | Presented as demo wallet content. |
| Savings goal progress | Yes | No | Planned for demo | Simulated local UI value only. |
| Recent wallet activity | Yes | No | Planned for demo | Must be synthetic and session-scoped. |
| `channel` | Optional display | Yes | Implemented | Allowed serving field. |
| `history_segment` | Technical mode only | Yes | Implemented | Coarse proxy segment only. |
| `newbie` | Technical mode only | Yes | Implemented | Small categorical serving signal. |
| Eligible offers | Technical mode only | Yes | Implemented | Already allowed by upstream rules. |
| Raw account balance | No | No | Out of scope | Must not be sent to Engine. |
| Direct identifiers | No | No | Out of scope | Demo uses generated session and request IDs. |
| Credit score, income, wealth, fraud, risk, compliance state | No | No | Out of scope | These are upstream governed responsibilities. |

## Decision Integration

ECloe Pay does not request eligibility and does not ask ECloe Engine to invent an offer. It receives the decision created during checkout.

The checkout flow calls:

```http
POST /v1/decisions
Idempotency-Key: demo-session:checkout:interaction
```

Example selected-offer state stored by the planned demo Backend-for-Frontend:

```json
{
  "session_id": "sess_demo_001",
  "request_id": "req_demo_001",
  "decision_id": "dec_demo_001",
  "offer_id": "cashback_recurring_purchase",
  "policy": "likelihood_ranker",
  "policy_version": "likelihood-v1",
  "purchase_likelihood": 0.1375
}
```

ECloe Pay uses this state to render the benefit. It must not create a new decision when the user simply opens the wallet screen.

## Reward Integration

After the simulated user interacts with the benefit, ECloe Pay registers a reward event through the implemented Engine endpoint:

```http
POST /v1/rewards
```

```json
{
  "decision_id": "dec_demo_001",
  "event_id": "evt_demo_001",
  "event_type": "conversion",
  "reward": 1.0,
  "occurred_at": "2026-07-26T12:00:00Z"
}
```

Demo reward mapping:

| User action | Event type | Demo reward | Pay state |
|:---|:---|---:|:---|
| Open benefit | `click` | `0.2` | Benefit viewed. |
| Dismiss benefit | `dismissal` | `0.0` | Benefit dismissed. |
| Accept benefit | `conversion` | `1.0` | Benefit accepted and recorded. |

These values are deterministic demo values. In a real integration, trusted backend services must map verified business events to configured reward values.

After reward acceptance, ECloe Pay may display:

```text
Your interaction was recorded and will be available for future policy evaluation.
```

It must not say that the model retrained immediately, that the next user will instantly receive a different offer, or that the Engine learned online from this single event.

## Demo Journey

| Step | Area | Status | Behavior |
|:---|:---|:---|:---|
| 1 | ECloe Market | Planned for demo | User adds an item to cart and reaches checkout. |
| 2 | Eligibility simulator | Planned for demo | Demo layer produces eligible wallet benefits. |
| 3 | ECloe Engine | Implemented | Engine ranks eligible offers and returns one selected offer. |
| 4 | ECloe Pay | Planned for demo | Wallet shows the selected benefit. |
| 5 | ECloe Pay | Planned for demo | User opens, dismisses, or accepts the benefit. |
| 6 | ECloe Engine | Implemented | Reward event is appended and linked to the original decision. |
| 7 | ECloe Control Room | Planned for demo | Technical timeline shows decision and reward evidence. |

## Azure Direction

The current repository documents a low-consumption Azure target architecture for the Engine and event storage. ECloe Pay should follow the same low-cost direction when implemented:

| Concern | MVP direction | Notes |
|:---|:---|:---|
| Frontend hosting | Azure Static Web Apps or App Service | Future demo UI hosting option. |
| Runtime integration | Demo Backend-for-Frontend | Aggregates session state and calls ECloe Engine. |
| Decision and reward events | Cosmos DB Serverless or Azure SQL Database serverless | Must preserve idempotency and append-only reward behavior. |
| Pay transactional state | Azure SQL Database | Dedicated `ecloe_pay` schema owns demo sessions, wallet snapshots, payment orders, benefit interactions, and outbox events. |
| Pay artifact bucket | Azure Blob Storage | Dedicated `ecloe-pay-demo-artifacts` bucket stores only demo-safe Pay evidence such as simulated receipts or screenshots. |
| Secrets | Azure Key Vault | Keeps API credentials and service configuration outside code. |
| Observability | Application Insights | Tracks UI actions, Engine latency, failures, and fallback mode without logging sensitive context. |

These are target architecture notes, not deployed infrastructure in the current repository.

## Real-Ready Azure SQL Implementation Plan

The next ECloe Pay implementation step prepares the demo for a real Azure SQL-backed validation flow without storing raw banking credentials, full account numbers, card data, CVV, credit scores, income, wealth, fraud signals, or governed eligibility decisions inside the demo surface.

### Database Ownership

| Azure SQL database | Application use | Notes |
|:---|:---|:---|
| `ecloe_validation` | ECloe Pay application data | Main validation database for identity, wallet, payment, reward, audit, integration, and migration state. |
| `master` | Azure SQL administration only | Holds server-level administration context. It must not store ECloe Pay domain tables, wallet state, sessions, payment orders, or reward evidence. |

`ecloe_validation` may share the same Azure SQL server with other ECloe surfaces for cost control, but schema ownership must stay explicit. ECloe Market must not write Pay-owned tables, and ECloe Pay must not write Market-owned tables directly.

### Target Schemas

| Schema | Responsibility | Planned tables |
|:---|:---|:---|
| `ecloe_pay_identity` | Login, user identity, credentials, sessions, consent, and security events. | `users`, `user_credentials`, `auth_sessions`, `login_attempts`, `user_consents`. |
| `ecloe_pay_wallet` | Tokenized wallet account references, balances, holds, ledger entries, and statements. | `bank_accounts`, `account_ledger_entries`, `account_holds`, `account_balance_snapshots`, `statement_items`. |
| `ecloe_pay_payments` | Payment order lifecycle, attempts, idempotency, and provider references. | `payment_orders`, `payment_attempts`, `payment_idempotency_keys`, `payment_provider_refs`, `payment_events`. |
| `ecloe_pay_rewards` | Wallet benefit interactions, cashback, savings goals, and Engine reward linkage. | `benefit_interactions`, `cashback_events`, `savings_goal_events`. |
| `ecloe_pay_audit` | Security, data access, and operational evidence. | `audit_events`, `security_events`, `data_access_events`. |
| `ecloe_pay_integration` | Provider connection references, webhooks, outbox records, and migrations. | `provider_connections`, `provider_webhook_events`, `outbox_events`, `schema_migrations`. |

The current `ecloe_pay` schema can remain as the compatibility schema for the implemented demo slice. New real-ready tables should be introduced through versioned migrations and then adopted behind repository interfaces.

### Money and Balance Rules

| Rule | Requirement |
|:---|:---|
| Monetary representation | Store amounts as integer cents, with explicit `currency`. |
| Source of truth | Use append-only ledger entries as the financial source of truth. Balance snapshots are read optimization only. |
| Holds | Reserve funds with `account_holds` before confirming a payment debit. |
| Idempotency | Require idempotency keys for payment creation, payment confirmation, provider callbacks, and reward-event writes. |
| External account data | Store only tokenized provider references, bank name, status, and safe display fields such as `account_last4`. |
| Sensitive fields | Do not store raw full account numbers, card numbers, CVV, banking passwords, credit score, income, wealth, fraud state, or compliance decision state. |

### Backend Implementation Layers

| Layer | Planned files | Responsibility |
|:---|:---|:---|
| Authentication service | `src/demo/ecloe_pay/services/auth_service.py` | Normalize email, validate password hashes, enforce login attempt controls, create/revoke sessions, and record security events. |
| Wallet service | `src/demo/ecloe_pay/services/wallet_service.py` | Calculate available balance, manage holds, append ledger entries, expose statements, and record cashback. |
| Payment service | `src/demo/ecloe_pay/services/payment_service.py` | Create payment orders, check available balance, reserve funds, confirm/reject attempts, and publish payment events. |
| Identity repository | `src/demo/ecloe_pay/repositories/identity.py` | Persist users, credentials, auth sessions, attempts, and consents. |
| Wallet repository | `src/demo/ecloe_pay/repositories/wallet.py` | Persist accounts, holds, ledger entries, snapshots, and statement rows. |
| Payment repository | `src/demo/ecloe_pay/repositories/payments.py` | Persist orders, attempts, idempotency keys, provider references, and payment events. |
| Audit repository | `src/demo/ecloe_pay/repositories/audit.py` | Persist security and data-access evidence without logging sensitive values. |

Flask routes should stay thin. They should validate request shape, call services, and return response DTOs. SQLAlchemy/T-SQL access should remain inside repository implementations.

### API Expansion

| Route | Purpose | Notes |
|:---|:---|:---|
| `POST /api/auth/login` | Validate login and create a session. | Must validate a password hash and record login attempts. |
| `POST /api/auth/logout` | Revoke the current session. | Must clear session cookies. |
| `GET /api/auth/me` | Restore authenticated UI state. | UI must not treat `localStorage` as the source of truth. |
| `GET /api/wallet` | Return safe wallet summary. | Returns available balance, cashback, savings goal, and account display metadata. |
| `GET /api/wallet/statement` | Return synthetic or provider-backed statement rows. | Must not expose raw provider payloads. |
| `POST /api/payments` | Create a payment order. | Requires authenticated session, idempotency key, active account, and sufficient available balance. |
| `GET /api/payments/{payment_order_id}` | Read payment status. | Returns safe status and timestamps. |

### Implementation Sequence

1. Add a versioned Azure SQL migration for the new schemas under `ecloe_validation`.
2. Keep `ECLOE_PAY_DATABASE_MODE=memory` as the default and make Azure SQL opt-in.
3. Introduce service-layer modules for authentication, wallet, and payments.
4. Split the current broad Pay repository contract into identity, wallet, payments, and audit repositories while preserving memory implementations for tests.
5. Move login validation to `auth_service` and keep session restoration through `/api/auth/me`.
6. Replace fixed wallet values with `/api/wallet` responses in the browser client.
7. Add ledger-based debit, hold, release, cashback, and statement logic.
8. Route payment simulation through `payment_service` so the demo and Azure SQL modes share one business contract.
9. Add tests for login validation, session restoration, insufficient funds, idempotent payment creation, ledger integrity, cashback entries, and forbidden sensitive schema fields.
10. Validate the Azure SQL path with a least-privilege runtime user, not `db_owner`.

## Acceptance Criteria

ECloe Pay is ready for the planned demo when:

- wallet screens use only synthetic session data;
- checkout decision state is reused instead of creating duplicate decisions;
- accepted, dismissed, and clicked benefits create deterministic reward events;
- customer-facing mode hides internal policy and artifact details;
- technical mode exposes request, decision, reward, and policy evidence;
- the UI never claims credit approval, eligibility approval, fraud detection, risk decisions, or immediate online learning;
- fallback presentation mode works when the local Engine API is unavailable.

## Implemented Static Demo Slice

The initial implementation lives in:

```text
src/demo/ecloe_pay/
```

Files:

| File | Purpose |
|:---|:---|
| `app.py` | Flask app with landing, wallet, session, terms, simulated payment, reset, and benefit interaction routes. |
| `landing.html` | ECloe Pay landing page explaining the simulated product, secure demo flow, private bucket, and Azure SQL ownership. |
| `index.html` | ECloe Pay wallet, benefit, activity, security, and terms UI. |
| `styles.css` | Responsive kawaii-inspired visual system for the static demo. |
| `app.js` | Browser client for Flask APIs, plus static fallback state, terms gate, simulated transaction validation, idempotency guard, and reward-event evidence. |
| `schema.sql` | Pay-owned Azure SQL `ecloe_pay` schema and dedicated Pay bucket record. |
| `repository.py` | Compatibility re-export for the Pay persistence package. |
| `repositories/` | PayRepository contract plus memory, Azure SQL, and factory implementations for simulated Pay state. |

The static slice deliberately does not create users, collect credentials, store real payment data, or call external financial services.

Run locally:

```powershell
.venv\Scripts\python.exe -m flask --app src.demo.ecloe_pay.app run --host 127.0.0.1 --port 5000
```

Create the dedicated private Azure Blob container:

```powershell
.\scripts\create_ecloe_pay_bucket.ps1
```

## Related Documentation

- [`demo-interface.md`](demo-interface.md) - Full planned ECloe Demo interface.
- [`api-contract.md`](api-contract.md) - Implemented Engine API payloads and validation rules.
- [`marketplace-finance-use-case.md`](marketplace-finance-use-case.md) - Practical marketplace-wallet scenario.
- [`cloud-setup.md`](cloud-setup.md) - Current low-consumption Azure storage setup.
- [`ecloe-pay-overview.svg`](ecloe-pay-overview.svg) - ECloe Pay overview diagram.
- [`ecloe-pay-transfer-flow.svg`](ecloe-pay-transfer-flow.svg) - ECloe Pay transfer flow diagram.
- [`ecloe-pay-simplified-relationship.svg`](ecloe-pay-simplified-relationship.svg) - ECloe Pay simplified relationship diagram.
