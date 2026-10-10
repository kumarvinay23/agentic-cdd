"""G3 — page classes + statement routing."""

from __future__ import annotations

from agetic_cdd_api.services_databook_extract import rows_from_table
from agetic_cdd_api.services_databook_harness import run_all_goldens, run_all_traps, run_trap
from agetic_cdd_api.services_databook_models import PageClass
from agetic_cdd_api.services_databook_pages import (
    classify_table_class,
    classify_text_to_page_class,
    page_class_to_statement,
    resolve_statement_label,
)


def test_classify_income_statement_table() -> None:
    hit = classify_table_class(table_name="Income Statement INR Cr")
    assert hit.page_class == PageClass.INCOME_STATEMENT
    assert page_class_to_statement(hit.page_class) == "income_statement"


def test_classify_note_page() -> None:
    hit = classify_text_to_page_class("Notes to the financial statements — accounting policies")
    assert hit.page_class == PageClass.NOTE
    assert page_class_to_statement(hit.page_class) == "note"


def test_notes_to_equity_statement_stays_note() -> None:
    """'Notes to … Equity' must not win as EQUITY via embedded title."""
    hit = classify_text_to_page_class("Notes to the Statement of Changes in Equity")
    assert hit.page_class == PageClass.NOTE


def test_sheet_shortcut_numeric_suffix() -> None:
    from agetic_cdd_api.services_databook_pages import classify_sheet_name

    for name in ("Sheet_IS_12", "IS12", "BS.1", "CF-2"):
        hit = classify_sheet_name(name)
        assert hit is not None, name
        assert hit.page_class != PageClass.UNKNOWN, name


def test_enrich_ignores_diagnostic_notes() -> None:
    from agetic_cdd_api.services_databook_models import PageKind, PageRegisterEntry
    from agetic_cdd_api.services_databook_pages import _enrich_page_class

    entry = PageRegisterEntry(
        page_id="x",
        filename="a.pdf",
        doc_id="d",
        page=1,
        kind=PageKind.MIXED,
        notes=["Sparse text with images — treated as scan/mixed; OCR not available"],
        sheet_name=None,
    )
    enriched = _enrich_page_class(entry)
    assert enriched.page_class == PageClass.UNKNOWN


def test_resolve_statement_from_table_when_header_weak() -> None:
    stmt, source, mismatch = resolve_statement_label(
        header_statement="table",
        table_class=PageClass.BALANCE_SHEET,
    )
    assert stmt == "balance_sheet"
    assert source == "table_name"
    assert mismatch is False


def test_extract_stamps_page_class_and_routes_statement() -> None:
    table = {
        "name": "P&L USD millions",
        "rows": [
            ["Metric", "FY2024"],
            ["Revenue", "72"],
        ],
    }
    rows = rows_from_table(source_name="a.pdf", doc_id="d", table=table)
    assert len(rows) == 1
    row = rows[0]
    assert row.page_class == PageClass.INCOME_STATEMENT
    assert row.statement == "income_statement"
    assert row.statement_source in {"table_name", "table_header"}
    assert row.metric_key == "revenue"


def test_misroute_balance_sheet_blocks_revenue_map() -> None:
    table = {
        "name": "Balance Sheet USD m",
        "rows": [
            ["Metric", "FY2024"],
            ["Revenue", "100"],
        ],
    }
    rows = rows_from_table(source_name="a.pdf", doc_id="d", table=table)
    assert len(rows) == 1
    assert rows[0].statement == "balance_sheet"
    assert rows[0].metric_key is None


def test_page_class_misroute_trap() -> None:
    result = run_trap(
        {
            "trap_id": "t35-local",
            "kind": "misroute",
            "check": "page_class_map",
            "caption": "Revenue",
            "table": {
                "name": "Balance Sheet USD m",
                "rows": [["Metric", "FY2024"], ["Revenue", "100"]],
            },
            "expect_statement": "balance_sheet",
            "expect_unmapped": True,
        }
    )
    assert result.ok, result.message


def test_golden_g3_assertions_pass() -> None:
    results = run_all_goldens()
    g3_failures = [
        f for r in results for f in r.failures if f.code.startswith("G3")
    ]
    assert not g3_failures, g3_failures


def test_g3_traps_pass() -> None:
    traps = run_all_traps()
    g3 = [t for t in traps if t.trap_id in {"t33", "t34", "t35", "t36"}]
    assert len(g3) == 4
    assert all(t.ok for t in g3), [t for t in g3 if not t.ok]
