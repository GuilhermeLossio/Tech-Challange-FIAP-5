from __future__ import annotations

import scripts.init_ecloe_pay_sql as init_sql


def test_init_ecloe_pay_sql_requires_explicit_non_placeholder_password(monkeypatch) -> None:
    monkeypatch.delenv("ECLOE_PAY_DEMO_USER_PASSWORD", raising=False)

    try:
        init_sql._require_explicit_demo_password()
    except RuntimeError as error:
        assert "must be set explicitly" in str(error)
    else:
        raise AssertionError("missing demo password should fail")

    monkeypatch.setenv("ECLOE_PAY_DEMO_USER_PASSWORD", init_sql.PLACEHOLDER_PASSWORD)
    try:
        init_sql._require_explicit_demo_password()
    except RuntimeError as error:
        assert "placeholder" in str(error)
    else:
        raise AssertionError("placeholder demo password should fail")

    monkeypatch.setenv("ECLOE_PAY_DEMO_USER_PASSWORD", "configured-secret-for-test")
    assert init_sql._require_explicit_demo_password() == "configured-secret-for-test"


def test_init_ecloe_pay_sql_prints_only_safe_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        init_sql,
        "initialize",
        lambda: init_sql.InitSummary(
            connection_ok=True,
            schema_ok=True,
            migrations_applied=1,
            persona_status="updated",
            seed_validation_ok=True,
        ),
    )

    assert init_sql.main() == 0
    output = capsys.readouterr().out

    assert "Azure SQL connection: OK" in output
    assert "Schema ecloe_pay: OK" in output
    assert "Migrations applied: 1" in output
    assert "Demo persona: updated" in output
    assert "Seed validation: OK" in output
    assert "password" not in output.lower()
    assert "token" not in output.lower()
    assert "connection string" not in output.lower()


def test_init_ecloe_pay_sql_has_operational_checks_and_deterministic_seed() -> None:
    source = init_sql.Path(init_sql.__file__).read_text(encoding="utf-8")

    assert "pyodbc.drivers()" in source
    assert "ODBC Driver 18" in source
    assert "get_token(SQL_TOKEN_SCOPE)" in source
    assert "SELECT 1" in source
    assert "schema_migrations" in source
    assert "generate_password_hash(password)" in source
    assert "snap_pay_demo_7841" in source
    assert "pay_order_demo_7841" in source
    assert "ECLOE_PAY_DEMO_USER_PASSWORD" in source
    assert "PLACEHOLDER_PASSWORD" in source
    assert "print(f\"ECloe Pay SQL initialization failed: {type(error).__name__}\"" in source
    assert "access_token" not in source.split("def main", 1)[-1]
