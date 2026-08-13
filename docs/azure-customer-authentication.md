# Azure Customer Authentication

ECloe Market and ECloe Pay use Microsoft Entra External ID for customer sign-up and sign-in in Azure. ECloe Engine keeps its separate bearer-token and scope boundary. Local development may use the existing synthetic credentials, but the cloud web runtime rejects local authentication and in-memory persistence.

## Security Model

The Flask application is a confidential backend-for-frontend. It starts an OpenID Connect Authorization Code flow with PKCE and stores the short-lived flow state in the Pay repository. The browser receives only an opaque flow cookie and, after callback validation, an opaque application-session cookie. Access tokens, ID tokens, passwords, real e-mail addresses, names, and raw Entra subjects are not persisted.

The local identity key is an HMAC of the normalized token issuer and `sub` claim. It selects a deterministic synthetic persona and links subsequent sign-ins to the same local user. The application stores the pseudonymized key in `ecloe_pay.external_identities`.

## External Tenant Setup

1. Create or select a Microsoft Entra tenant configured for external customers.
2. Register a confidential web application for the ECloe demo.
3. Create a customer sign-up and sign-in user flow with e-mail and password plus self-service password reset.
4. Register `https://<demo-host>/auth/callback` as the production redirect URI.
5. Register `http://localhost:5000/auth/callback` only for explicit local External ID testing.
6. Configure the production post-logout URI as `https://<demo-host>/`.
7. Do not collect address, phone, financial, CPF, card, bank-account, or custom financial attributes in the user flow.
8. Put the confidential client secret in Azure Key Vault and grant the demo Container App managed identity the Key Vault Secrets User role for that secret.

Required application settings are documented in `.env.example`. Production uses the `ECLOE_WEB_*` variables and obtains `ECLOE_WEB_ENTRA_CLIENT_SECRET` through a Container Apps Key Vault secret reference.

## Runtime Flow

| Step | Behavior |
|:---|:---|
| `GET /auth/login` | Validates the local return path, creates a ten-minute single-use OIDC flow, and redirects to External ID. |
| `GET /auth/callback` | Consumes the flow, lets MSAL validate the response, pseudonymizes the identity, and provisions or loads the synthetic account. |
| Application session | Stores only a random token in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie; Azure SQL stores its hash. |
| `POST /api/auth/logout` | Requires CSRF, revokes the local session, clears cookies, and returns the External ID logout URL. |

The absolute session lifetime is eight hours, the idle timeout is thirty minutes, and a successful callback always rotates any existing application session.

## Synthetic Account Provisioning

`data/demo/ecloe_user_personas.json` contains versioned demo personas for a new customer, recurring buyer, saver, and benefit-oriented customer. First login creates the synthetic user, profile, wallet account, transaction history, and audit evidence transactionally. `/api/reset` restores the same deterministic persona.

All displayed balances, cashback, transactions, names, locations, and segments are fictional. ECloe does not create realistic CPF, card, branch, or bank-account numbers and does not connect to Open Finance.

## Operations

- Run `python -m scripts.init_ecloe_pay_sql` with a migration identity before deploying a revision that requires the new schema.
- Keep Pay and Market on Azure SQL with Managed Identity in cloud; memory mode is local-only.
- Monitor result codes and pseudonymized user IDs only. Never log claims, authorization responses, cookies, or profile payloads.
- Disable a compromised customer by setting `ecloe_pay.demo_users.is_active` to `0`, then revoke their rows in `auth_sessions`.
- Delete expired `oidc_login_flows` regularly; writes also remove expired rows opportunistically.
- Rotate the Key Vault client secret before expiration and create a new Container App revision after the reference is updated.
- Customer deletion must remove dependent demo sessions and synthetic account data before deleting the external identity mapping and user row. The External ID customer account is managed separately in the Entra admin center.

## Verification

Automated tests mock the identity provider and verify state consumption, return-path validation, session revocation, deterministic provisioning, and absence of real claims or tokens in persisted data. A protected GitHub Environment may add an end-to-end smoke account for the external tenant; it must not place credentials in repository variables or logs.

Microsoft references: [External ID overview](https://learn.microsoft.com/en-us/entra/external-id/external-identities-overview), [authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), and [Python Flask sign-in tutorial](https://learn.microsoft.com/en-us/entra/identity-platform/tutorial-web-app-python-flask-sign-in-out).
