from __future__ import annotations

import argparse
import html
import secrets
import string
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from werkzeug.security import generate_password_hash

from scripts.init_ecloe_pay_sql import (
    _apply_schema,
    _engine_with_entra_token,
    _entra_access_token,
    _seed_deterministic_demo_state,
    _validate_odbc_driver,
)
from src.core.config import load_settings
from src.demo.ecloe_pay.repositories.base import normalize_email, user_id_for_email

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XLSX_PATH = ROOT / "data" / "demo" / "ecloe_pay_login_seed.local.xlsx"
REQUIRED_COLUMNS = (
    "full_name",
    "email",
    "password",
    "address_line1",
    "city",
    "state_region",
    "postal_code",
    "country",
    "phone",
    "preferred_language",
    "persona_label",
    "market_segment",
    "wallet_status",
    "is_active",
)
SAFE_SUMMARY_LABEL = "ECloe Pay XLSX seed"
LOCAL_XLSX_SUFFIX = ".local.xlsx"
PASSWORD_ALPHABET = string.ascii_letters + string.digits


@dataclass(frozen=True)
class LoginSeedRow:
    full_name: str
    email: str
    password: str
    address_line1: str
    city: str
    state_region: str
    postal_code: str
    country: str
    phone: str
    preferred_language: str
    persona_label: str
    market_segment: str
    wallet_status: str
    is_active: bool

    @property
    def email_normalized(self) -> str:
        return normalize_email(self.email)

    @property
    def user_id(self) -> str:
        return user_id_for_email(self.email_normalized)

    @property
    def display_name(self) -> str:
        return self.full_name


def default_seed_rows() -> list[dict[str, object]]:
    rows = [
        {
            "full_name": "Cloe Mercado",
            "email": "demo.market@ecloe.local",
            "address_line1": "Rua das Palmeiras, 426",
            "city": "Sao Paulo",
            "state_region": "SP",
            "postal_code": "01310-000",
            "country": "Brazil",
            "phone": "+55 11 94026-0001",
            "preferred_language": "pt-BR",
            "persona_label": "Synthetic marketplace-wallet validation persona",
            "market_segment": "recurring_customer",
            "wallet_status": "active",
            "is_active": True,
        },
        {
            "full_name": "Marina Costa",
            "email": "marina.costa.demo@ecloe.local",
            "address_line1": "Avenida Paulista, 1000",
            "city": "Sao Paulo",
            "state_region": "SP",
            "postal_code": "01310-100",
            "country": "Brazil",
            "phone": "+55 11 94026-0002",
            "preferred_language": "pt-BR",
            "persona_label": "Synthetic recurring shopper persona",
            "market_segment": "high_frequency_marketplace",
            "wallet_status": "active",
            "is_active": True,
        },
        {
            "full_name": "Lucas Almeida",
            "email": "lucas.almeida.demo@ecloe.local",
            "address_line1": "Rua Sete de Setembro, 180",
            "city": "Rio de Janeiro",
            "state_region": "RJ",
            "postal_code": "20050-002",
            "country": "Brazil",
            "phone": "+55 21 94026-0003",
            "preferred_language": "pt-BR",
            "persona_label": "Synthetic wallet reactivation persona",
            "market_segment": "returning_customer",
            "wallet_status": "review",
            "is_active": True,
        },
        {
            "full_name": "Avery Smith",
            "email": "avery.smith.demo@ecloe.local",
            "address_line1": "315 Market Street",
            "city": "San Francisco",
            "state_region": "CA",
            "postal_code": "94105",
            "country": "United States",
            "phone": "+1 415 555 0426",
            "preferred_language": "en-US",
            "persona_label": "Synthetic cross-border marketplace persona",
            "market_segment": "new_marketplace_customer",
            "wallet_status": "active",
            "is_active": True,
        },
    ]
    for row in rows:
        row["password"] = _random_demo_password()
    return rows


def generate_seed_xlsx(path: Path = DEFAULT_XLSX_PATH) -> Path:
    _require_local_xlsx_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_xlsx(path, default_seed_rows())
    return path


def write_xlsx(path: Path, rows: list[dict[str, object]]) -> None:
    table = [list(REQUIRED_COLUMNS)]
    for row in rows:
        table.append([_cell_value(row[column]) for column in REQUIRED_COLUMNS])
    sheet_rows = [_sheet_row(index, values) for index, values in enumerate(table, start=1)]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _worksheet_xml("".join(sheet_rows)))


def load_seed_rows(path: Path) -> list[LoginSeedRow]:
    _require_local_xlsx_path(path)
    raw_rows = read_xlsx(path)
    if not raw_rows:
        raise ValueError("XLSX seed file is empty.")
    header = [value.strip() for value in raw_rows[0]]
    missing = sorted(set(REQUIRED_COLUMNS) - set(header))
    if missing:
        raise ValueError(f"XLSX seed file is missing required columns: {missing}")
    indexes = {column: header.index(column) for column in REQUIRED_COLUMNS}
    rows = []
    seen_emails = set()
    for line_number, values in enumerate(raw_rows[1:], start=2):
        payload = {column: _value_at(values, indexes[column]) for column in REQUIRED_COLUMNS}
        email = normalize_email(payload["email"])
        if not email:
            raise ValueError(f"Row {line_number} has a blank email.")
        if email in seen_emails:
            raise ValueError(f"Duplicate seed email at row {line_number}: {email}")
        seen_emails.add(email)
        if not payload["password"]:
            raise ValueError(f"Row {line_number} has a blank password.")
        payload["email"] = email
        payload["is_active"] = _parse_bool(payload["is_active"], line_number)
        rows.append(LoginSeedRow(**payload))  # type: ignore[arg-type]
    if not rows:
        raise ValueError("XLSX seed file must contain at least one persona row.")
    return rows


def read_xlsx(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("xl/worksheets/sheet1.xml")
    root = ElementTree.fromstring(xml)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows = []
    for row in root.findall(".//x:sheetData/x:row", namespace):
        values_by_index = {}
        for cell in row.findall("x:c", namespace):
            ref = cell.attrib.get("r", "")
            index = _column_index("".join(ch for ch in ref if ch in string.ascii_letters))
            text = cell.findtext("x:is/x:t", default="", namespaces=namespace)
            values_by_index[index] = text
        if values_by_index:
            max_index = max(values_by_index)
            rows.append([values_by_index.get(index, "") for index in range(max_index + 1)])
    return rows


def import_seed_xlsx(path: Path = DEFAULT_XLSX_PATH) -> tuple[int, str]:
    _require_local_xlsx_path(path)
    rows = load_seed_rows(path)
    settings = load_settings()
    _validate_odbc_driver(settings.ecloe_pay_sql_driver)
    access_token = _entra_access_token(settings.ecloe_pay_sql_auth_mode)
    engine = _engine_with_entra_token(settings, access_token)
    primary_user_id = rows[0].user_id
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            _apply_schema(connection)
            for row in rows:
                upsert_seed_row(connection, row, generate_password_hash(row.password))
            _seed_deterministic_demo_state(connection, primary_user_id)
        except Exception:
            transaction.rollback()
            raise
        else:
            transaction.commit()
    return len(rows), primary_user_id


def upsert_seed_row(connection: Any, row: LoginSeedRow, password_hash: str) -> None:
    from sqlalchemy import text

    params = seed_sql_params(row, password_hash)
    connection.execute(
        text(
            """
            IF NOT EXISTS (
                SELECT 1 FROM ecloe_pay.demo_users WHERE email_normalized = :email_normalized
            )
            BEGIN
                INSERT INTO ecloe_pay.demo_users (
                    user_id, email_normalized, display_name, persona_label, password_hash,
                    is_active, is_demo, pii_allowed
                )
                VALUES (
                    :user_id, :email_normalized, :display_name, :persona_label, :password_hash,
                    :is_active, 1, 0
                )
            END
            ELSE
            BEGIN
                UPDATE ecloe_pay.demo_users
                SET display_name = :display_name,
                    persona_label = :persona_label,
                    password_hash = :password_hash,
                    is_active = :is_active,
                    is_demo = 1,
                    pii_allowed = 0,
                    updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                WHERE email_normalized = :email_normalized
            END
            """
        ),
        params,
    )
    connection.execute(
        text(
            """
            IF NOT EXISTS (
                SELECT 1 FROM ecloe_pay.demo_user_profiles WHERE user_id = :user_id
            )
            BEGIN
                INSERT INTO ecloe_pay.demo_user_profiles (
                    user_id, full_name, address_line1, city, state_region, postal_code,
                    country, phone, preferred_language, market_segment, wallet_status,
                    masking_enabled
                )
                VALUES (
                    :user_id, :full_name, :address_line1, :city, :state_region, :postal_code,
                    :country, :phone, :preferred_language, :market_segment, :wallet_status, 1
                )
            END
            ELSE
            BEGIN
                UPDATE ecloe_pay.demo_user_profiles
                SET full_name = :full_name,
                    address_line1 = :address_line1,
                    city = :city,
                    state_region = :state_region,
                    postal_code = :postal_code,
                    country = :country,
                    phone = :phone,
                    preferred_language = :preferred_language,
                    market_segment = :market_segment,
                    wallet_status = :wallet_status,
                    masking_enabled = 1,
                    updated_at = TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
                WHERE user_id = :user_id
            END
            """
        ),
        params,
    )


def seed_sql_params(row: LoginSeedRow, password_hash: str) -> dict[str, object]:
    return {
        "user_id": row.user_id,
        "email_normalized": row.email_normalized,
        "display_name": row.display_name,
        "persona_label": row.persona_label,
        "password_hash": password_hash,
        "is_active": int(row.is_active),
        "full_name": row.full_name,
        "address_line1": row.address_line1,
        "city": row.city,
        "state_region": row.state_region,
        "postal_code": row.postal_code,
        "country": row.country,
        "phone": row.phone,
        "preferred_language": row.preferred_language,
        "market_segment": row.market_segment,
        "wallet_status": row.wallet_status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or import ECloe Pay login seed XLSX data.")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX_PATH)
    parser.add_argument("--generate", action="store_true", help="Generate the local unmasked XLSX file.")
    parser.add_argument("--import-sql", action="store_true", help="Import the XLSX into Azure SQL.")
    args = parser.parse_args(argv)

    try:
        if args.generate:
            path = generate_seed_xlsx(args.xlsx)
            rows = load_seed_rows(path)
            print(f"{SAFE_SUMMARY_LABEL}: generated")
            print(f"Rows: {len(rows)}")
            print(f"Path: {path}")
            return 0
        if not args.import_sql:
            args.import_sql = True
        count, primary_user_id = import_seed_xlsx(args.xlsx)
    except Exception as error:
        print(f"{SAFE_SUMMARY_LABEL} failed: {type(error).__name__}", file=sys.stderr)
        return 1

    print(f"{SAFE_SUMMARY_LABEL}: imported")
    print(f"Rows: {count}")
    print(f"Primary user id: {primary_user_id}")
    print("Plaintext passwords stored in SQL: no")
    return 0


def _cell_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _sheet_row(row_index: int, values: list[str]) -> str:
    cells = []
    for column_index, value in enumerate(values):
        cell_ref = f"{_column_name(column_index)}{row_index}"
        cells.append(
            f'<c r="{cell_ref}" t="inlineStr"><is><t>{html.escape(value)}</t></is></c>'
        )
    return f'<row r="{row_index}">{"".join(cells)}</row>'


def _worksheet_xml(sheet_rows: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheetData>{sheet_rows}</sheetData>"
        "</worksheet>"
    )


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="login_seed" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )


def _column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _column_index(name: str) -> int:
    index = 0
    for char in name.upper():
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _value_at(values: list[str], index: int) -> str:
    return values[index].strip() if index < len(values) else ""


def _parse_bool(value: str, line_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Row {line_number} has an invalid is_active value.")


def _random_demo_password(length: int = 24) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def _require_local_xlsx_path(path: Path) -> None:
    if not path.name.endswith(LOCAL_XLSX_SUFFIX):
        raise ValueError(f"XLSX seed path must end with {LOCAL_XLSX_SUFFIX}.")


if __name__ == "__main__":
    raise SystemExit(main())
