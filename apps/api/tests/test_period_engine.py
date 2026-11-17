"""Derived totals and periods come from the stored months and the fiscal year end."""

import datetime as dt

from openpyxl import Workbook

from agetic_cdd_api.services_fact_repository import Fact
from agetic_cdd_api.services_ontology import load_ontology
from agetic_cdd_api.services_period_engine import _save, derive_periods, run_period_engine
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


def test_invalid_ytd_months_covered_does_not_abort_save() -> None:
    """Contract refuses YTD with 12 months; period engine must soft-skip, not crash ingest."""
    bad = Fact(
        "fin.pl.revenue",
        100.0,
        "CURRENCY",
        "YTD",
        "2025-01-01",
        "2025-12-31",
        12,
        "ACTUAL",
        {},
        "doc-bad-ytd",
        "B",
        [],
        status="DERIVED",
        currency="USD",
        derived_from=["f-src"],
        formula="bad ytd",
        fact_id="fact-bad-ytd-12",
    )
    assert _save(bad, "period-soft-skip") is None


def test_full_year_latest_actual_does_not_emit_ytd() -> None:
    """When latest actual is fiscal year-end, emit FY — never YTD with 12 months."""
    months = []
    for month, day in enumerate((31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31), start=1):
        end = dt.date(2025, month, day).isoformat()
        months.append(
            Fact(
                "fin.pl.revenue",
                10.0,
                "CURRENCY",
                "FM",
                f"2025-{month:02d}-01",
                end,
                1,
                "ACTUAL",
                {},
                "doc-fy",
                "B",
                [],
                status="SELECTED",
                currency="USD",
                fact_id=f"fact-fm-{month}",
            )
        )
    derived = derive_periods(
        months,
        load_ontology(),
        latest_actual=dt.date(2025, 12, 31),
        fye_month=12,
    )
    assert any(f.period_type == "FY" and f.months_covered == 12 for f in derived)
    assert not any(f.period_type == "YTD" for f in derived)


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
