"""Phase 2 — page register, dual extract, unread honesty."""

from __future__ import annotations

from agetic_cdd_api.services_databook_dual import (
    merge_dual_extract,
    parse_number_method_b,
    rows_from_table_method_b,
)
from agetic_cdd_api.services_databook_extract import rows_from_table
from agetic_cdd_api.services_databook_models import (
    ExtractedRow,
    MetricFamily,
    PageKind,
    RowStatus,
    SourceRef,
)
from agetic_cdd_api.services_databook_pages import classify_page_kind
from agetic_cdd_api.services_databook_prove import assign_proof_levels


def test_classify_page_kinds() -> None:
    kind, unread, _ = classify_page_kind(char_count=0, has_images=False)
    assert kind == PageKind.BLANK and unread
    kind, unread, _ = classify_page_kind(char_count=0, has_images=True)
    assert kind == PageKind.IMAGE and unread
    kind, unread, _ = classify_page_kind(char_count=40, has_images=True)
    assert kind == PageKind.MIXED and unread
    kind, unread, _ = classify_page_kind(char_count=500, has_images=False)
    assert kind == PageKind.TEXT and not unread
    kind, unread, _ = classify_page_kind(
        char_count=0, has_images=True, is_standalone_image=True
    )
    assert kind == PageKind.IMAGE and unread


def test_parse_number_method_b_independent() -> None:
    assert parse_number_method_b("(1,234.5)") == -1234.5
    assert parse_number_method_b("12.5%") == 12.5
    assert parse_number_method_b("$3,140") == 3140.0
    # Annotated accounting negatives (footnote / currency outside parens).
    assert parse_number_method_b("(125.4) *") == -125.4
    assert parse_number_method_b("(£450.00)a") == -450.0
    assert parse_number_method_b(" (1,234) note") == -1234.0


def test_format_number_for_cell_avoids_scientific() -> None:
    from agetic_cdd_api.services_databook_dual import _format_number_for_cell
    from agetic_cdd_api.services_databook_extract import _parse_number

    for value in (1_000_000.0, 0.00012, 3140.5, -12_500.0):
        cell = _format_number_for_cell(value)
        assert "e" not in cell.lower()
        assert _parse_number(cell) == value


def test_agree_key_separates_duplicate_captions() -> None:
    """Same caption in different tables must not cross-pair Method B peers."""
    from agetic_cdd_api.services_databook_dual import _agree_key

    a = ExtractedRow(
        row_id="a1",
        doc_id="d",
        source_name="a.pdf",
        caption="Operating Expenses",
        metric_key="opex",
        metric_family=MetricFamily.OTHER,
        fiscal_year=2024,
        value=100.0,
        table_name="Budget",
        statement="income_statement",
    )
    b = ExtractedRow(
        row_id="b1",
        doc_id="d",
        source_name="a.pdf",
        caption="Operating Expenses",
        metric_key="opex",
        metric_family=MetricFamily.OTHER,
        fiscal_year=2024,
        value=999.0,
        table_name="Actuals",
        statement="income_statement",
    )
    assert _agree_key(a) != _agree_key(b)
    merged = merge_dual_extract([a], [b])
    # No peer in the same table → not a disagreement.
    assert merged[0].read_dual_agree is None
    assert merged[0].assumption is False


def test_dual_extract_preserves_title_band_with_unit_banner() -> None:
    """Title above years must stay so header scale/currency survive Method B."""
    from agetic_cdd_api.services_databook_dual import dual_extract_table

    table = {
        "name": "P&L",
        "rows": [
            ["Consolidated income statement (USD Millions)"],
            ["Metric", "FY2023", "FY2024"],
            ["Revenue", "100", "110"],
            ["EBITDA", "20", "25"],
        ],
    }
    merged = dual_extract_table(source_name="a.xlsx", doc_id="d", table=table)
    rev = [r for r in merged if r.metric_key == "revenue" and r.fiscal_year == 2024]
    assert rev
    assert rev[0].read_dual_agree is True
    assert rev[0].currency == "USD" or rev[0].scale in {"M", "m"} or rev[0].scale == "M"


def test_dual_extract_agrees_on_clean_table() -> None:
    table = {
        "name": "Income Statement INR Cr",
        "sheet_index": 1,
        "rows": [
            ["Metric", "FY2023", "FY2024"],
            ["Revenue", "2800", "3140"],
            ["EBITDA", "500", "620"],
        ],
    }
    a = rows_from_table(source_name="a.xlsx", doc_id="d", table=table)
    b = rows_from_table_method_b(source_name="a.xlsx", doc_id="d", table=table)
    merged = merge_dual_extract(a, b)
    assert merged
    rev = [r for r in merged if r.metric_key == "revenue" and r.fiscal_year == 2024]
    assert rev
    assert rev[0].read_dual_agree is True
    assert "A" in rev[0].extract_methods and "B" in rev[0].extract_methods
    assert rev[0].source_ref is not None
    assert rev[0].source_ref.bbox is not None
    assert len(rev[0].source_ref.bbox) == 4


def test_dual_extract_monthly_bs_preserves_dates_and_agrees() -> None:
    """Date-band rewrite must not turn ``2025-12-31`` into bare ``2025``.

    Also: Method B table suffix must not stamp scale=B (billions) via ``#B``.
    """
    from agetic_cdd_api.services_databook_dual import dual_extract_table

    # Minimal monthly BS: year band + date band + Dec snapshots + bare FY cols.
    table = {
        "name": "Monthly BS",
        "rows": [
            ["", "", "2024", "2024", "2024", "2024", "2025"],
            [
                "",
                "Account",
                "2024-01-31 00:00:00",
                "2024-06-30 00:00:00",
                "2024-12-31 00:00:00",
                "2025-06-30 00:00:00",
                "2025-12-31 00:00:00",
            ],
            ["", "Cash", "1000000", "1100000", "3219514.26", "2500000", "2667782.2"],
            ["", "Accounts Receivable", "500000", "600000", "1200336.62", "900000", "1222501.9"],
        ],
    }
    merged = dual_extract_table(source_name="pack.xlsx", doc_id="d", table=table)
    cash = [r for r in merged if r.metric_key == "cash" and r.fiscal_year == 2025]
    assert cash, "expected Dec-2025 cash"
    assert cash[0].read_dual_agree is True
    assert cash[0].assumption is False
    assert cash[0].scale == "M"
    assert abs(float(cash[0].value) - 2.6677822) < 1e-6
    # Must not emit one row per month for the same FY.
    assert len(cash) == 1


def test_dual_extract_disagreement_marks_assumption() -> None:
    """Method B sees a different value → read_dual_agree False + assumption."""
    a_row = ExtractedRow(
        row_id="a1",
        doc_id="d",
        source_name="a.pdf",
        caption="Revenue",
        metric_key="revenue",
        metric_family=MetricFamily.REVENUE,
        fiscal_year=2024,
        value=100.0,
        status=RowStatus.CANDIDATE,
        extract_methods=["A"],
        source_ref=SourceRef(doc="a.pdf", row=1, col=1, rule="year_column"),
    )
    b_row = ExtractedRow(
        row_id="b1",
        doc_id="d",
        source_name="a.pdf",
        caption="Revenue",
        metric_key="revenue",
        metric_family=MetricFamily.REVENUE,
        fiscal_year=2024,
        value=999.0,
        status=RowStatus.CANDIDATE,
        extract_methods=["B"],
    )
    merged = merge_dual_extract([a_row], [b_row])
    assert merged[0].read_dual_agree is False
    assert merged[0].assumption is True
    proved = assign_proof_levels(merged, block_fail_ids=set(), hold_ids=set())
    assert proved[0].proof_level is not None
    assert proved[0].proof_level.value == "L1"
    assert "read_dual_disagree" in (proved[0].proof_checks or [])


def test_extract_pdf_emits_pages_metadata(tmp_path) -> None:
    """Scanned-like empty PDF pages are classified unread."""
    from pypdf import PdfWriter

    from agetic_cdd_api.services_extract import extract_file

    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as fh:
        writer.write(fh)

    result = extract_file(path)
    assert result["page_count"] >= 1
    assert isinstance(result.get("pages"), list)
    assert result["pages"]
    assert result["pages"][0]["unread"] is True


def test_xlsx_each_sheet_is_table(tmp_path) -> None:
    from openpyxl import Workbook

    from agetic_cdd_api.services_extract import extract_file

    path = tmp_path / "multi.xlsx"
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "P&L"
    ws1.append(["Metric", "FY2024"])
    ws1.append(["Revenue", 100])
    ws2 = wb.create_sheet("Balance")
    ws2.append(["Metric", "FY2024"])
    ws2.append(["Cash", 50])
    wb.save(path)

    result = extract_file(path)
    assert len(result["tables"]) == 2
    assert {t["name"] for t in result["tables"]} == {"P&L", "Balance"}
    assert result["tables"][0].get("sheet_index") == 1
    assert len(result["pages"]) == 2
