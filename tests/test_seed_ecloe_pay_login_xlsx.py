from __future__ import annotations

from werkzeug.security import check_password_hash

import scripts.seed_ecloe_pay_login_xlsx as seed_xlsx


def test_seed_xlsx_generator_writes_unmasked_local_seed_file(tmp_path) -> None:
    path = tmp_path / "ecloe_pay_login_seed.local.xlsx"

    generated = seed_xlsx.generate_seed_xlsx(path)
    rows = seed_xlsx.load_seed_rows(generated)

    assert generated == path
    assert len(rows) >= 4
    assert rows[0].email == "demo.market@ecloe.local"
    assert rows[0].password == seed_xlsx._deterministic_password(rows[0].email)
    assert rows[0].address_line1 == "Rua das Palmeiras, 426"
    assert set(seed_xlsx.REQUIRED_COLUMNS) <= set(seed_xlsx.read_xlsx(path)[0])


def test_seed_xlsx_validation_rejects_duplicate_email_and_blank_password(tmp_path) -> None:
    duplicate_path = tmp_path / "duplicate.local.xlsx"
    blank_password_path = tmp_path / "blank.local.xlsx"
    rows = seed_xlsx.default_seed_rows()
    rows[1]["email"] = rows[0]["email"]
    seed_xlsx.write_xlsx(duplicate_path, rows)

    try:
        seed_xlsx.load_seed_rows(duplicate_path)
    except ValueError as error:
        assert "Duplicate seed email" in str(error)
    else:
        raise AssertionError("duplicate seed email should fail")

    rows = seed_xlsx.default_seed_rows()
    rows[0]["password"] = ""
    seed_xlsx.write_xlsx(blank_password_path, rows)

    try:
        seed_xlsx.load_seed_rows(blank_password_path)
    except ValueError as error:
        assert "blank password" in str(error)
    else:
        raise AssertionError("blank seed password should fail")


def test_seed_sql_params_hash_password_and_never_include_plaintext_password() -> None:
    row = seed_xlsx.LoginSeedRow(**seed_xlsx.default_seed_rows()[0])
    password_hash = seed_xlsx.generate_password_hash(row.password)

    params = seed_xlsx.seed_sql_params(row, password_hash)

    assert "password" not in params
    assert params["password_hash"] != row.password
    assert check_password_hash(params["password_hash"], row.password)
    assert params["email_normalized"] == "demo.market@ecloe.local"
    assert params["address_line1"] == "Rua das Palmeiras, 426"


def test_seed_xlsx_generate_summary_does_not_print_sensitive_values(tmp_path, capsys) -> None:
    path = tmp_path / "seed.local.xlsx"

    assert seed_xlsx.main(["--generate", "--xlsx", str(path)]) == 0
    output = capsys.readouterr().out

    assert "generated" in output
    assert "Rows: 4" in output
    assert rows_passwords_not_in_output(path, output)
    assert "Rua das Palmeiras" not in output
    assert "demo.market@ecloe.local" not in output


def rows_passwords_not_in_output(path, output: str) -> bool:
    return all(row.password not in output for row in seed_xlsx.load_seed_rows(path))
