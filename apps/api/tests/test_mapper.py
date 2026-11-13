"""The mapper keeps section choices and queues every guess."""

import datetime as dt

from openpyxl import Workbook

from agetic_cdd_api.services_mapper import record_mappings
from agetic_cdd_api.services_ontology import load_ontology
from agetic_cdd_api.services_statement_reader import read_statement_grid

_KINDS = {"LINE", "SUM", "ARITH", "RATIO"}


def test_a_loan_under_current_liabilities_stays_current_and_guesses_are_queued() -> None:
    values, formulas = _balance_sheet()
    _statement, _facts, log, _checks, _items = read_statement_grid(
        values, formulas, "doc-step7", load_ontology(), "USD", 1, {}, fye_month=12
    )
    mapped = record_mappings(log, "step7-map", "doc-step7")
    loan = next(row for row in mapped["decisions"] if row["label_as_read"] == "Bank loan")
    facility = next(row for row in mapped["decisions"] if row["label_as_read"] == "Term loan facility")
    assert loan["concept_id"] == "fin.bs.borrowings_current"
    assert facility["concept_id"] == "fin.bs.borrowings_current"
    assert loan["ontology_version"] == load_ontology().version

    lines = [row for row in log if row["row_kind"] in _KINDS]
    queued = {(row["sheet"], row["row"]) for row in mapped["review_queue"]}
    decided = {(row["sheet"], row["row"]) for row in mapped["decisions"]}
    for row in lines:
        key = (row["sheet"], row["row"])
        assert row.get("concept_id") or key in queued
        assert key in decided or key in queued
    guesses = [row for row in lines if row.get("concept_id") and (row["confidence"] < 0.7 or row.get("alternative"))]
    assert guesses
    assert all((row["sheet"], row["row"]) in queued for row in guesses)
    assert ("BS", 7) in queued
    assert "Mystery item" not in {row["label_as_read"] for row in mapped["decisions"]}


def _balance_sheet():
    book = Workbook()
    sheet = book.active
    sheet.title = "BS"
    for index, month in enumerate(range(1, 7), start=2):
        sheet.cell(1, index, dt.datetime(2025, month, 28))
    rows = {
        2: ("Total assets", 100),
        3: ("Total liabilities", 40),
        4: ("Current liabilities", None),
        5: ("Bank loan", 10),
        6: ("Term loan facility", 7),
        7: ("Mystery item", 3),
    }
    for row, (label, value) in rows.items():
        sheet.cell(row, 1, label)
        if value is None:
            continue
        for column in range(2, 8):
            sheet.cell(row, column, value)
    formulas = Workbook()
    other = formulas.active
    other.title = sheet.title
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is not None:
                other.cell(cell.row, cell.column, cell.value)
    return sheet, other
