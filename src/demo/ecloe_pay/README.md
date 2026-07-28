# ECloe Pay Demo Frontend

This folder contains the first static ECloe Pay implementation slice.

Run it with Flask:

```powershell
.venv\Scripts\python.exe -m flask --app src.demo.ecloe_pay.app run --host 127.0.0.1 --port 5000
```

Then open:

```text
http://127.0.0.1:5000/
http://127.0.0.1:5000/pay
```

The root route shows the landing page. The `/pay` route opens the runnable wallet
demo. The HTML can still be opened directly in a browser as a fallback
presentation mode. It does not require account creation, does not call a payment
provider, and does not process real money.

Implemented in this slice:

- simulated wallet home;
- selected eligible benefit;
- mandatory demo terms;
- secure simulated payment confirmation;
- deterministic reward-event evidence;
- technical mode with decision and bucket metadata;
- Flask API routes for session state, terms, simulated payment orders, reset,
  and benefit interactions;
- optional demo-persona login;
- Azure SQL-compatible schema for Pay-owned state under the `ecloe_pay` schema.

The default repository mode is memory and does not require SQL dependencies:

```text
ECLOE_PAY_DATABASE_MODE=memory
```

Azure SQL persistence is opt-in for local validation or cloud runtime:

```text
ECLOE_PAY_DATABASE_MODE=azure_sql
ECLOE_PAY_SQL_SERVER=ecloe-sql-1266.database.windows.net
ECLOE_PAY_SQL_DATABASE=ecloe_validation
ECLOE_PAY_SQL_AUTH_MODE=azure_cli
```

Use `entra_interactive` only for local development, `azure_cli` after `az login`,
and `managed_identity` in cloud. The demo login persona is synthetic and must not
be confused with a real banking account.

Apply the Azure SQL schema and seed the demo persona with:

```powershell
python scripts\migrate_ecloe_pay_azure_sql.py
```

The planned dedicated artifact bucket is `ecloe-pay-demo-artifacts`. The SQL
schema also records this bucket name so Pay exports and demo evidence do not
share Market or Engine storage ownership.

Create the private Azure Blob container with:

```powershell
.\scripts\create_ecloe_pay_bucket.ps1
```

For local Azure SQL validation, open only the current client IP:

```powershell
.\scripts\allow_ecloe_pay_sql_current_ip.ps1
```
