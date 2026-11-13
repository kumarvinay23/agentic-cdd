"""Phase 1: ontology-backed `/view` and `/lines` read API."""

from __future__ import annotations

import os

import pytest

from agetic_cdd_api.services_databook_view import build_databook_lines, build_databook_view
from agetic_cdd_api.services_ontology import load_ontology

_DEAL = "slice-a-view"


def test_missing_ontology_deal_is_not_building(monkeypatch) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_view.settings.databook_database_url",
        "postgresql://example/databook",
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_view._deal_row",
        lambda _url, _deal_id: None,
    )
    view = build_databook_view("missing-deal")
    assert view.status == "unpublished"
    assert view.totals.building == 0
    assert view.series == {}


def test_view_without_databook_url_is_unpublished(monkeypatch) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_view.settings.databook_database_url",
        "",
    )
    view = build_databook_view(_DEAL)
    assert view.status == "unpublished"
    assert view.series == {}
    assert view.totals.rows == 0
    lines = build_databook_lines(_DEAL)
    assert lines.rows == []


def test_view_and_lines_from_postgres_fixture() -> None:
    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("databook URL is not set")
    _load(url)

    view = build_databook_view(_DEAL)
    assert view.status == "ready"
    assert view.reporting_currency == "USD"
    assert view.actual_through == 2025
    assert "revenue" in view.series
    assert view.series["revenue"]["2025"].value == 100.0
    assert view.series["revenue"]["2025"].fact_id == "fact-slice-a-revenue"
    assert view.series["ebitda"]["2025"].value == 20.0
    assert view.totals.rows >= 2
    assert view.totals.mapped_rows >= 2
    assert view.totals.metrics >= 2
    assert any(f.file == "accounts.xlsx" for f in view.files)

    # Conflict between SELECTED revenue and a CANDIDATE with a different value.
    assert "revenue|2025" in view.dq_cells
    conflict_ns = {i.n for i in view.dq_cells["revenue|2025"] if i.kind == "conflict"}
    assert conflict_ns

    lines = build_databook_lines(_DEAL)
    assert len(lines.rows) >= 3
    for row in lines.rows:
        assert isinstance(row.period, int)
        assert isinstance(row.scale_applied, bool)
    revenue = next(r for r in lines.rows if r.metric == "revenue" and r.period == 2025 and r.value == 100.0)
    assert revenue.statement == "schedule"
    assert revenue.sheet == "PL"
    assert revenue.scale_applied is True
    line_ns = {i.n for r in lines.rows for i in r.dq}
    assert conflict_ns <= line_ns

    narrowed = build_databook_lines(_DEAL, q="EBITDA")
    assert narrowed.rows and all("ebitda" in r.line_item.lower() or r.metric == "ebitda" for r in narrowed.rows)
    unmapped = build_databook_lines(_DEAL, unmapped=True)
    assert all(r.metric == "" for r in unmapped.rows)


def _load(url: str) -> None:
    from agetic_cdd_api.services_databook_migrate import psql
    from agetic_cdd_api.services_ontology import insert_deal

    psql(
        url,
        f"DELETE FROM record WHERE deal_id = '{_DEAL}'; "
        f"DELETE FROM flag WHERE deal_id = '{_DEAL}'; "
        f"DELETE FROM reconciliation WHERE deal_id = '{_DEAL}'; "
        f"DELETE FROM mapping_decision WHERE deal_id = '{_DEAL}'; "
        f"DELETE FROM source_location WHERE doc_id IN (SELECT doc_id FROM document WHERE deal_id = '{_DEAL}'); "
        f"DELETE FROM fact WHERE deal_id = '{_DEAL}'; "
        f"DELETE FROM document WHERE deal_id = '{_DEAL}'; "
        f"DELETE FROM deal WHERE deal_id = '{_DEAL}';",
    )
    insert_deal(
        url,
        {
            "deal_id": _DEAL,
            "reporting_currency": "USD",
            "fiscal_year_end": "12-31",
            "latest_actual_month": "2025-12-31",
        },
    )
    version = load_ontology().version
    psql(
        url,
        "INSERT INTO document (doc_id, deal_id, ontology_version, file_name, format, doc_type, status, evidence_tier) "
        f"VALUES ('doc-slice-a', '{_DEAL}', '{version}', 'accounts.xlsx', 'xlsx', 'FIN_MGMT_ACCOUNTS', 'READ', 'B'); "
        "INSERT INTO source_location (location_id, doc_id, sheet_or_page, cell_range, row_label_as_read, value_as_read, extraction_method) "
        "VALUES "
        "('loc-slice-a-rev', 'doc-slice-a', 'PL', 'B2', 'Revenue', '100', 'STATEMENT_READER'), "
        "('loc-slice-a-ebitda', 'doc-slice-a', 'PL', 'B10', 'EBITDA', '20', 'STATEMENT_READER'), "
        "('loc-slice-a-rev-alt', 'doc-slice-a', 'PL', 'C2', 'Revenue', '80', 'STATEMENT_READER'); "
        "INSERT INTO fact (fact_id, deal_id, entity_id, ontology_version, concept_id, value, unit_type, currency, "
        "scale_applied, period_type, period_start, period_end, months_covered, fiscal_year, basis, dimensions, "
        "status, evidence_tier, source_location_ids, derived_from) "
        f"VALUES "
        f"('fact-slice-a-revenue', '{_DEAL}', 'CONSOLIDATED', '{version}', 'fin.pl.revenue', 100, 'CURRENCY', 'USD', "
        f"1, 'FY', DATE '2025-01-01', DATE '2025-12-31', 12, 2025, 'ACTUAL', '{{}}'::jsonb, 'SELECTED', 'B', "
        f"ARRAY['loc-slice-a-rev'], ARRAY[]::text[]), "
        f"('fact-slice-a-ebitda', '{_DEAL}', 'CONSOLIDATED', '{version}', 'fin.pl.ebitda', 20, 'CURRENCY', 'USD', "
        f"1, 'FY', DATE '2025-01-01', DATE '2025-12-31', 12, 2025, 'ACTUAL', '{{}}'::jsonb, 'SELECTED', 'B', "
        f"ARRAY['loc-slice-a-ebitda'], ARRAY[]::text[]), "
        f"('fact-slice-a-revenue-alt', '{_DEAL}', 'CONSOLIDATED', '{version}', 'fin.pl.revenue', 80, 'CURRENCY', 'USD', "
        f"1, 'FY', DATE '2025-01-01', DATE '2025-12-31', 12, 2025, 'ACTUAL', '{{}}'::jsonb, 'CANDIDATE', 'B', "
        f"ARRAY['loc-slice-a-rev-alt'], ARRAY[]::text[]);",
    )
