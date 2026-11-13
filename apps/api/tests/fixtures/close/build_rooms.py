"""Write the five Close fixture rooms next to this file.

Captions are ontology synonyms. Figures are answer-key amounts for the fixtures
only. The statement reader keeps a sheet when its captions match a P&L, balance
sheet, or cash-flow signature, The rent room carries revenue, gross profit, and rent as valued lines. A caption
with no amounts is read as a section header and would pull the rows under it
into that header's concept. The borrowings room carries total assets, total
equity, and short-term debt, and assets equal equity plus that debt.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent

# A one-page PDF with an empty content stream. There is no text layer to map.
_BLANK_PDF = b"""%PDF-1.1
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 300]/Contents 4 0 R>>endobj
4 0 obj<</Length 0>>stream
endstream
endobj
trailer<</Root 1 0 R>>
%%EOF
"""


def main() -> None:
    _room(
        "room_01",
        currency="USD",
        fye="12-31",
        latest="2025-12-31",
        sector_pack="fuel_retail",
        deal_type="statements",
        expected=["PL", "BS", "CF"],
        start=(2025, 1),
        amounts={"Revenue": 100, "Gross profit": 40, "Total assets": 500, "Total equity": 200, "Net change in cash": 10},
    )
    _room(
        "room_02",
        currency="EUR",
        fye="06-30",
        latest="2025-06-30",
        sector_pack="healthcare_clinic",
        deal_type="statements",
        expected=["PL", "BS", "CF"],
        start=(2024, 7),
        amounts={"Revenue": 70, "Gross profit": 25, "Total assets": 300, "Total equity": 90, "Net change in cash": 4},
    )
    _room(
        "room_03",
        currency="USD",
        fye="12-31",
        latest="2025-12-31",
        sector_pack="payments",
        deal_type="statements",
        expected=["PL", "BS", "CF"],
        start=(2025, 1),
        amounts={"Revenue": 55, "Gross profit": 20, "Total assets": 400, "Total equity": 150, "Net change in cash": 8},
        extra_sheet=("TAM", {"Addressable market": 999, "Revenue": 999}),
        unread=["scan.pdf"],
    )
    _room(
        "room_04",
        currency="GBP",
        fye="03-31",
        latest="2025-03-31",
        sector_pack="recurring_collection",
        deal_type="lease",
        expected=["PL"],
        start=(2024, 4),
        amounts={"Revenue": 20, "Gross profit": 20, "Rent expense": 6},
        workbook="rent.xlsx",
    )
    _room(
        "room_05",
        currency="USD",
        fye="12-31",
        latest="2025-12-31",
        sector_pack="fuel_retail",
        deal_type="debt",
        expected=["BS"],
        start=(2025, 1),
        amounts={"Total assets": 180, "Total equity": 140, "Short-term debt": 40},
        workbook="borrowings.xlsx",
    )


def _room(
    name: str,
    *,
    currency: str,
    fye: str,
    latest: str,
    sector_pack: str,
    deal_type: str,
    expected: list[str],
    start: tuple[int, int],
    amounts: dict[str, int],
    workbook: str = "statements.xlsx",
    extra_sheet: tuple[str, dict[str, int]] | None = None,
    unread: list[str] | None = None,
) -> None:
    folder = ROOT / name
    folder.mkdir(parents=True, exist_ok=True)
    months = _months(*start, 12)
    groups = {
        "PL": ["Revenue", "Gross profit", "Rent expense"],
        "BS": ["Total assets", "Total equity", "Short-term debt"],
        "CF": ["Net change in cash"],
    }
    book = Workbook()
    used = False
    for statement, labels in groups.items():
        rows = [(label, amounts[label]) for label in labels if label in amounts]
        if not rows:
            continue
        sheet = book.active if not used else book.create_sheet(statement)
        used = True
        sheet.title = statement
        _grid(sheet, months, rows)
    if extra_sheet:
        title, rows = extra_sheet
        sheet = book.create_sheet(title)
        _grid(sheet, months, list(rows.items()))
    book.save(folder / workbook)
    for file_name in unread or []:
        (folder / file_name).write_bytes(_BLANK_PDF)
    profile = {
        "reporting_currency": currency,
        "fiscal_year_end": fye,
        "latest_actual_month": latest,
        "sector_pack": sector_pack,
        "deal_type": deal_type,
        "expected_statements": expected,
        "workbook": workbook,
    }
    if unread:
        profile["unread"] = unread
    (folder / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")


def _grid(sheet, months: list[dt.datetime], rows: list[tuple[str, int]]) -> None:
    for index, month in enumerate(months, start=2):
        sheet.cell(1, index, month)
    for row_index, (label, value) in enumerate(rows, start=2):
        sheet.cell(row_index, 1, label)
        for column in range(2, 2 + len(months)):
            sheet.cell(row_index, column, value)


def _months(year: int, month: int, count: int) -> list[dt.datetime]:
    dates = []
    for _ in range(count):
        nxt = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
        dates.append(dt.datetime.combine(nxt - dt.timedelta(days=1), dt.time()))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return dates


if __name__ == "__main__":
    main()
