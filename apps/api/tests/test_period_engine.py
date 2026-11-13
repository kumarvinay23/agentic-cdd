"""Derived totals and periods come from the stored months and the fiscal year end."""

import datetime as dt

from openpyxl import Workbook

from agetic_cdd_api.services_ontology import load_ontology
from agetic_cdd_api.services_period_engine import run_period_engine
from agetic_cdd_api.services_statement_reader import read_statement_grid

_POLICY = {
    "include_other_operating_income": False,
    "rent_basis": "GAAP",
    "bad_debt_in_ebitda": False,
}


def test_source_totals_match_or_are_reconciled_and_periods_follow_the_year_end() -> None:
    values, formulas = _statement()
    _statement_name, facts, _log, _checks, items = read_statement_grid(
        values, formulas, "doc-step8", load_ontology(), "USD", 1, {}, fye_month=12
    )
    result = run_period_engine(
        facts,
        deal_id="step8-engine",
        policy=_POLICY,
        latest_actual=dt.date(2025, 6, 30),
        fye_month=12,
        items_by_stmt={item["rn"]: item for item in items},
    )
    stored = result["facts"]
    assert stored
    assert not any(row["period_type"] == "FY" for row in stored)

    revenue = [row for row in stored if row["concept_id"] == "fin.pl.revenue" and row["status"] == "DERIVED" and row["period_type"] == "YTD"]
    assert len(revenue) == 1
    assert revenue[0]["months_covered"] == 6
    assert revenue[0]["value"] == 60

    annual = [row for row in stored if row["status"] == "COMPARATIVE" and row["reason_code"] == "DUPLICATE"]
    assert annual
    assert all(row["period_type"] == "YTD" for row in annual)

    monthly = [row for row in result["comparisons"] if row["concept"] == "fin.pl.gross_profit" and row["period_type"] == "FM"]
    assert any(row["passed"] for row in monthly)
    failed = [row for row in monthly if row["passed"] is False]
    assert len(failed) == 1
    assert failed[0]["diff"] == 3
    assert len(result["reconciliations"]) == 1
    recon = result["reconciliations"][0]
    assert recon["variance"] == 3
    assert recon["explanation"]
    assert recon["selected_fact_id"]
    assert recon["comparative_fact_id"]


def _statement():
    values = Workbook()
    sheet = values.active
    sheet.title = "PL"
    formulas = Workbook()
    other = formulas.active
    other.title = "PL"
    for month, day in enumerate((31, 28, 31, 30, 31, 30), start=1):
        stamp = dt.datetime(2025, month, day)
        sheet.cell(1, month + 1, stamp)
        other.cell(1, month + 1, stamp)
    sheet.cell(1, 8, "FY2025")
    other.cell(1, 8, "FY2025")
    for row, label in ((2, "Revenue"), (3, "Cost of sales"), (4, "Gross profit")):
        sheet.cell(row, 1, label)
        other.cell(row, 1, label)
    for column in range(2, 8):
        letter = chr(64 + column)
        sheet.cell(2, column, 10)
        other.cell(2, column, 10)
        sheet.cell(3, column, 4)
        other.cell(3, column, 4)
        sheet.cell(4, column, 9 if column == 7 else 6)
        other.cell(4, column, f"={letter}2-{letter}3")
    sheet.cell(2, 8, 60)
    other.cell(2, 8, 60)
    return sheet, other
