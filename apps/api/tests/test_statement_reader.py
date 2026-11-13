"""Statement readers store lines with a source cell and hold spreadsheet errors."""

import datetime as dt
from types import SimpleNamespace

from openpyxl import Workbook

from agetic_cdd_api.services_ontology import load_ontology
from agetic_cdd_api.services_statement_reader import read_excel, read_pdf, read_room, read_statement_grid, store_lines

_MONTHS = [
    dt.datetime(2025, 1, 31),
    dt.datetime(2025, 2, 28),
    dt.datetime(2025, 3, 31),
    dt.datetime(2025, 4, 30),
    dt.datetime(2025, 5, 31),
    dt.datetime(2025, 6, 30),
]


def test_excel_lines_keep_a_source_cell_and_errors_are_held(tmp_path) -> None:
    path = tmp_path / "statement.xlsx"
    _workbook(path)
    onto = load_ontology()
    locs: dict = {}
    facts = read_excel(path, "doc-step6-excel", onto, "USD", locs, scale=1, fye_month=12)
    stored = store_lines(facts, locs, "step6-excel")

    assert stored
    assert all(row["source_location_ids"] and locs[row["source_location_ids"][0]].cell_range for row in stored)
    held = [row for row in stored if row["status"] == "HELD"]
    assert len(held) == 2
    assert all(row["value"] is None and row["reason_code"] == "FORMULA_ERROR" for row in held)
    detail = " ".join(row["reason_detail"] for row in held)
    assert "#REF!" in detail and "#DIV/0!" in detail
    revenue = [row["value"] for row in stored if row["concept_id"] == "fin.pl.revenue" and row["status"] == "SELECTED"]
    assert sorted(revenue) == [10, 11, 12, 13]


def test_sum_rows_are_not_stored_as_chosen_values() -> None:
    values, formulas = _workbook(None)
    for column in range(2, 8):
        letter = chr(64 + column)
        formulas.cell(3, column, f"=SUM({letter}2:{letter}2)")
    onto = load_ontology()
    locs: dict = {}
    _statement, facts, _log, _checks, _items = read_statement_grid(
        values, formulas, "doc-step6-sum", onto, "USD", 1, locs, fye_month=12
    )
    stored = store_lines(facts, locs, "step6-sum")
    assert any(fact.status == "COMPARATIVE" and fact.reason_code == "SOURCE_SUBTOTAL" for fact in facts)
    # Series-mapped source subtotals (gross profit) may land as COMPARATIVE for denser UI series;
    # they are never SELECTED.
    assert all(row["status"] in {"SELECTED", "HELD", "COMPARATIVE"} for row in stored)
    assert all(row["status"] != "SELECTED" or row["value"] not in {4, 5, 6} for row in stored)
    assert all(locs[row["source_location_ids"][0]].cell_range for row in stored)


def test_slice_d_maps_nine_series_captions_and_assumes_currency(tmp_path) -> None:
    """Dense PL+BS captions map to the Financial-history series; missing ISO inherits reporting currency."""
    from agetic_cdd_api.services_statement_reader import is_non_statement_sheet

    path = tmp_path / "history.xlsx"
    _dense_workbook(path)
    onto = load_ontology()
    locs: dict = {}
    facts = read_excel(path, "doc-slice-d", onto, "GBP", locs, scale=1, fye_month=12)
    stored = store_lines(facts, locs, "slice-d-dense")

    concepts = {row["concept_id"] for row in stored if row["status"] in {"SELECTED", "COMPARATIVE"}}
    expected = {
        "fin.pl.revenue",
        "fin.pl.cost_of_sales",
        "fin.pl.gross_profit",
        "fin.pl.ebitda",
        "fin.pl.operating_income",
        "fin.pl.net_income",
        "fin.bs.cash",
        "fin.bs.total_assets",
        "fin.bs.equity",
    }
    assert expected <= concepts
    assumed = [
        row
        for row in stored
        if (row.get("mapping") or {}).get("currency_source") == "assumed" and row.get("currency") == "GBP"
    ]
    assert assumed
    assert is_non_statement_sheet("TAM sizing")
    assert is_non_statement_sheet("ESG metrics")
    assert not is_non_statement_sheet("P&L")
    from agetic_cdd_api.services_statement_reader import is_non_statement_document

    assert is_non_statement_document("CONTRACT_CUSTOMER")
    assert is_non_statement_document("CAP_TABLE")
    assert is_non_statement_document("HR_PAYROLL_EXTRACT")
    assert not is_non_statement_document("FIN_MGMT_ACCOUNTS")
    assert not is_non_statement_document("FIN_QOE_REPORT")
    assert not is_non_statement_document("CORPORATE_DOCS")


def test_non_statement_sheet_is_declined(tmp_path) -> None:
    path = tmp_path / "mixed.xlsx"
    book = Workbook()
    tam = book.active
    tam.title = "TAM"
    for index, month in enumerate(_MONTHS, start=2):
        tam.cell(1, index, month)
    tam["A2"] = "Revenue"
    for index, value in enumerate([999, 999, 999, 999, 999, 999], start=2):
        tam.cell(2, index, value)
    pl = book.create_sheet("PL")
    for index, month in enumerate(_MONTHS, start=2):
        pl.cell(1, index, month)
    pl["A2"] = "Revenue"
    for index, value in enumerate([10, 11, 12, 13, 14, 15], start=2):
        pl.cell(2, index, value)
    pl["A3"] = "Gross profit"
    for index, value in enumerate([4, 4, 5, 5, 6, 6], start=2):
        pl.cell(3, index, value)
    book.save(path)

    onto = load_ontology()
    locs: dict = {}
    facts = read_excel(path, "doc-slice-d-decline", onto, "USD", locs, scale=1, fye_month=12)
    revenue = [f for f in facts if f.concept_id == "fin.pl.revenue" and f.status == "SELECTED"]
    assert sorted(f.value for f in revenue) == [10, 11, 12, 13, 14, 15]
    assert all(f.value != 999 for f in revenue)


def test_pdf_table_uses_the_statement_grid(tmp_path) -> None:
    path = tmp_path / "statement.pdf"
    _table_pdf(path)
    onto = load_ontology()
    locs: dict = {}
    outcome = read_pdf(path, "doc-step6-pdf", onto, "USD", locs, scale=1, fye_month=12)
    stored = store_lines(outcome["facts"], locs, "step6-pdf")
    assert outcome["status"] == "READ"
    revenue = [row for row in stored if row["concept_id"] == "fin.pl.revenue"]
    assert sorted(row["value"] for row in revenue) == [10, 11, 12, 13, 14, 15]
    assert all(locs[row["source_location_ids"][0]].cell_range for row in stored)


def test_image_only_pdf_stays_unread(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_deals.deals_root", lambda: tmp_path)
    deal = SimpleNamespace(slug="step6-room", id="step6-room")
    docs = tmp_path / "step6-room" / "documents"
    docs.mkdir(parents=True)
    _workbook(docs / "statement.xlsx")
    _blank_pdf(docs / "scan.pdf")

    result = read_room(deal, currency="USD")
    scan = next(row for row in result["rows"] if row["file_name"] == "scan.pdf")
    assert scan["status"] == "SKIPPED"
    assert scan["status_reason"] in {
        "no text returned",
        "non-statement document type",
        "pdf document type is not statement-shaped",
        "pdf file name is not statement-shaped",
        "pdf statement extract deferred",
    }
    assert result["facts"]
    assert all(row["value"] != 0 or row["status"] != "HELD" for row in result["facts"])
    assert all(row["source_location_ids"] for row in result["facts"])


def _workbook(path):
    book = Workbook()
    sheet = book.active
    sheet.title = "PL"
    for index, month in enumerate(_MONTHS, start=2):
        sheet.cell(1, index, month)
    sheet["A2"] = "Revenue"
    for index, value in enumerate([10, 11, 12, 13, "#REF!", "#DIV/0!"], start=2):
        sheet.cell(2, index, value)
    sheet["A3"] = "Gross profit"
    for index, value in enumerate([4, 4, 5, 5, 6, 6], start=2):
        sheet.cell(3, index, value)
    if path is not None:
        book.save(path)
        return sheet, sheet
    return sheet, _copy(sheet)


def _dense_workbook(path) -> None:
    """Generic PL + BS grid covering the nine Financial-history series captions."""
    book = Workbook()
    pl = book.active
    pl.title = "PL"
    # No currency symbol in the title band — reader must inherit reporting currency.
    pl["A1"] = "Income statement"
    for index, month in enumerate(_MONTHS, start=2):
        pl.cell(1, index, month)
    rows = [
        ("Revenue", [100, 101, 102, 103, 104, 105]),
        ("Cost of sales", [40, 41, 42, 43, 44, 45]),
        ("Gross profit", [60, 60, 60, 60, 60, 60]),
        ("EBITDA", [25, 26, 27, 28, 29, 30]),
        ("Operating profit", [20, 21, 22, 23, 24, 25]),
        ("Profit for the year", [12, 13, 14, 15, 16, 17]),
    ]
    for row_index, (label, values) in enumerate(rows, start=2):
        pl.cell(row_index, 1, label)
        for column, value in enumerate(values, start=2):
            pl.cell(row_index, column, value)

    bs = book.create_sheet("BS")
    bs["A1"] = "Balance sheet"
    for index, month in enumerate(_MONTHS, start=2):
        bs.cell(1, index, month)
    bs_rows = [
        ("Cash and cash equivalents", [8, 8, 9, 9, 10, 10]),
        ("Total assets", [200, 201, 202, 203, 204, 205]),
        ("Total equity", [90, 91, 92, 93, 94, 95]),
    ]
    for row_index, (label, values) in enumerate(bs_rows, start=2):
        bs.cell(row_index, 1, label)
        for column, value in enumerate(values, start=2):
            bs.cell(row_index, column, value)
    book.save(path)


def _copy(sheet):
    book = Workbook()
    other = book.active
    other.title = sheet.title
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is not None:
                other.cell(cell.row, cell.column, cell.value)
    return other


def _table_pdf(path) -> None:
    import fitz

    document = fitz.open()
    page = document.new_page(width=900, height=400)
    rows = [
        ["", "31 Jan 2025", "28 Feb 2025", "31 Mar 2025", "30 Apr 2025", "31 May 2025", "30 Jun 2025"],
        ["Revenue", "10", "11", "12", "13", "14", "15"],
        ["Gross profit", "4", "4", "5", "5", "6", "6"],
    ]
    columns = [40, 160, 280, 400, 520, 640, 760]
    for row_index, row in enumerate(rows):
        for column, text in enumerate(row):
            if text:
                page.insert_text((columns[column], 80 + row_index * 24), text, fontsize=9)
    document.save(path)
    document.close()


def _blank_pdf(path) -> None:
    import fitz

    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()
