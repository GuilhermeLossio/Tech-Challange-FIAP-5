# ECloe Pay Demo Frontend

This folder contains the first static ECloe Pay implementation slice.

Run it with Flask:

```powershell
$env:APP_ENVIRONMENT="local"
$env:ECLOE_WEB_AUTH_MODE="local"
.venv\Scripts\python.exe -m flask --app "src.demo.ecloe_pay.app:create_server_app" run --host 127.0.0.1 --port 5000
```

Then open:

```text
http://127.0.0.1:5000/
http://127.0.0.1:5000/pay
```

The root route shows the landing page. The `/pay` route redirects to
`/pay/login` until the demo persona is authenticated. The HTML can still be
opened directly in a browser as a fallback
presentation mode. In that mode the UI explicitly says
`Presentation mode — data is not being persisted.` and does not claim that login,
terms, or payment state was saved in Azure SQL. It does not require account
creation, does not call a payment provider, and does not process real money.

Implemented in this slice:

- simulated wallet home;
- selected eligible benefit;
- mandatory demo terms;
- secure simulated payment confirmation;
- deterministic reward-event evidence;
- technical mode with decision and bucket metadata;
- Flask API routes for session state, terms, simulated payment orders, reset,
  and benefit interactions;
- required demo-persona login before wallet access;
- secure simulated authentication with HttpOnly session-token cookies, CSRF
  checks, logout revocation, and login attempt limits;
- Azure SQL-compatible schema for Pay-owned state under the `ecloe_pay` schema;
- repository-based persistence with memory and Azure SQL implementations behind
  the same PayRepository contract.

The default repository mode is memory and does not require SQL dependencies.
Use it for CI and local automated tests, not as the intended authenticated
browser demo:

```text
ECLOE_PAY_DATABASE_MODE=memory
ECLOE_WEB_AUTH_MODE=local
```

Use `ECLOE_WEB_AUTH_MODE=entra_external` only after replacing the placeholder
`ECLOE_WEB_ENTRA_*` values with a real Microsoft Entra External ID tenant,
client ID, and client secret. Placeholder values such as
`https://seu-tenant.ciamlogin.com` are rejected during startup.

Use `ECLOE_WEB_AUTH_MODE=local_signup` when Microsoft Entra is not available and
the demo should provide its own lightweight e-mail/password registration backed
by Azure SQL. This mode is allowed in cloud only with Azure SQL persistence.

In External ID mode the login screen shows both `Entrar` and `Criar conta`.
Both actions redirect to Microsoft Entra External ID; ECloe never collects or
stores customer passwords. After the callback, ECloe creates the synthetic Pay
account only if that external subject has not already been linked.

New accounts start with the configured synthetic balance:

```text
ECLOE_PAY_INITIAL_BALANCE_CENTS=50000
```

Signup abuse control uses shared Redis rate limiting. Raw IP addresses are never
stored: the app normalizes the client IP from `X-Forwarded-For` and stores only
an HMAC hash for audit purposes. Multiple legitimate accounts may be created
from the same IP.

Azure SQL persistence is the intended mode for validating the browser login
flow against the configured demo persona:

```text
ECLOE_PAY_DATABASE_MODE=azure_sql
ECLOE_PAY_SQL_SERVER=ecloe-sql-1266.database.windows.net
ECLOE_PAY_SQL_DATABASE=ecloe_validation
ECLOE_PAY_SQL_AUTH_MODE=azure_cli
```

By default the Pay login uses the shared ECloe demo persona email
`demo.market@ecloe.local`, matching the planned ECloe Market login. Set
`ECLOE_DEMO_USER_EMAIL` and `ECLOE_DEMO_USER_PASSWORD` to share one demo
identity across Market and Pay, or use the Pay-specific
`ECLOE_PAY_DEMO_USER_EMAIL` and `ECLOE_PAY_DEMO_USER_PASSWORD` variables when
the Pay surface needs an explicit override.

For multi-persona login seeding, generate a local unmasked XLSX file:

```powershell
python -m scripts.seed_ecloe_pay_login_xlsx --generate
```

The generated `data/demo/ecloe_pay_login_seed.local.xlsx` file contains
simulated plaintext passwords and profile data for local preparation only. It is
ignored by Git. Import it into Azure SQL with:

```powershell
python -m scripts.seed_ecloe_pay_login_xlsx --xlsx data/demo/ecloe_pay_login_seed.local.xlsx
```

Or have the SQL initializer import it after applying the schema:

```powershell
$env:ECLOE_PAY_LOGIN_SEED_XLSX="data/demo/ecloe_pay_login_seed.local.xlsx"
python -m scripts.init_ecloe_pay_sql
```

Only password hashes are stored in Azure SQL. Profile fields are stored in
`ecloe_pay.demo_user_profiles`; sensitive columns use Azure SQL Dynamic Data
Masking, and the routine Pay runtime identity should not receive `UNMASK`.

Use `entra_interactive` only for local development, `azure_cli` after `az login`,
and `managed_identity` in cloud. The demo login persona is synthetic and must not
be confused with a real banking account.

Apply pending Azure SQL migrations and seed the deterministic demo state with:

```powershell
python -m scripts.init_ecloe_pay_sql
```

`/pay` and the Pay APIs require the demo persona login. In Azure SQL mode,
credentials are validated against `ecloe_pay.demo_users`. The raw session token
is only sent to the browser as the
`ecloe_pay_session` HttpOnly cookie; repositories store only its SHA-256 hash.
Mutable Pay routes require the `X-CSRF-Token` header paired with the
`ecloe_pay_csrf` cookie.

The planned dedicated artifact bucket is `ecloe-pay-demo-artifacts`. The SQL
schema also records this bucket name so Pay exports and demo evidence do not
share Market or Engine storage ownership.

## Real-ready Azure SQL direction

The next implementation step keeps `ecloe_validation` as the application
database and leaves `master` for Azure SQL administration only. Application
tables should be separated into identity, wallet, payments, rewards, audit, and
integration schemas. The current `ecloe_pay` schema remains the implemented demo
compatibility schema until those migrations are introduced behind repository
interfaces.

Balances should be controlled through ledger entries and temporary holds, not by
mutating a single balance field as the source of truth. Payment orders must use
idempotency keys, and linked account records must store only tokenized provider
references plus safe display metadata such as bank name and account last four
digits. Do not store raw bank-account numbers, card numbers, CVV, banking
passwords, credit scores, income, wealth, fraud state, or compliance decision
state in this demo surface.

Create the private Azure Blob container with:

```powershell
.\scripts\create_ecloe_pay_bucket.ps1
```

For local Azure SQL validation, open only the current client IP:

```powershell
.\scripts\allow_current_sql_client_ip.ps1
```

If the server has `publicNetworkAccess` disabled and local development access is
required, enable it only through the guarded prompt:

```powershell
.\scripts\allow_current_sql_client_ip.ps1 -EnablePublicNetworkAccess
```

Remove the local firewall rule after development:

```powershell
.\scripts\remove_current_sql_client_ip.ps1
```

Manual Azure SQL smoke test:

1. Run `az login`.
2. Run `.\scripts\allow_current_sql_client_ip.ps1` to allow only the current public IP.
3. Confirm `ODBC Driver 18 for SQL Server` is installed.
4. Configure local `ECLOE_PAY_DATABASE_MODE=azure_sql`, `ECLOE_PAY_SQL_SERVER`, `ECLOE_PAY_SQL_DATABASE`, `ECLOE_PAY_SQL_AUTH_MODE=azure_cli`, `ECLOE_PAY_SQL_DRIVER`, `ECLOE_PAY_DEMO_USER_EMAIL`, and an explicit `ECLOE_PAY_DEMO_USER_PASSWORD`.
5. Run `python -m scripts.init_ecloe_pay_sql`.
6. Start Flask with `.venv\Scripts\python.exe -m flask --app "src.demo.ecloe_pay.app:create_server_app" run --host 127.0.0.1 --port 5000`.
7. Open `http://127.0.0.1:5000/pay/login` and authenticate the demo persona.
8. Open `http://127.0.0.1:5000/pay`, accept the terms, and register a benefit interaction.
9. Simulate payment with confirmation code `0426`.
10. Repeat the same payment request and confirm idempotency blocks the duplicate.
11. Confirm `ecloe_pay.payment_orders`, `ecloe_pay.benefit_interactions`, and `ecloe_pay.outbox_events` in Azure SQL.
12. Log out and confirm authenticated routes return `401`.
13. Run `.\scripts\remove_current_sql_client_ip.ps1`.
