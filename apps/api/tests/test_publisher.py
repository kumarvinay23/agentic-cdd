"""Published cells come from the databook view and keep a source cell."""

import os

import pytest

from agetic_cdd_api.services_ontology import load_ontology
from agetic_cdd_api.services_publisher import publish, write_cell

_DEAL = "step11-publish"


def test_a_cell_without_a_source_cannot_be_published_and_a_gap_is_gov_05() -> None:
    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("databook URL is not set")
    _load(url)
    published = publish(_DEAL)
    cells = published["tabs"]["FDD-06"]
    revenue = next(cell for cell in cells if cell["concept_id"] == "fin.pl.revenue")
    assert revenue["fact_id"] == "fact-step11-revenue"
    assert revenue["cell_range"] == "B2"
    assert all(cell["concept_id"] != "fin.pl.da" for cell in cells)
    with pytest.raises(ValueError, match="source cell"):
        write_cell({"fact_id": "fact-step11-da", "concept_id": "fin.pl.da", "value": 1, "cell_range": None})
    gaps = published["tabs"]["GOV-05"]
    assert any(gap["fields"]["issue"].startswith("fin.pl.opex") and "FDD-06" in gap["fields"]["affected_exhibits"] for gap in gaps)
    from agetic_cdd_api.services_databook_migrate import psql

    stored = psql(url, f"SELECT record_class FROM record WHERE deal_id = '{_DEAL}' AND record_class = 'data_gap';")
    assert "data_gap" in stored.stdout


def _load(url: str) -> None:
    from agetic_cdd_api.services_databook_migrate import psql
    from agetic_cdd_api.services_ontology import insert_deal

    psql(
        url,
        "DELETE FROM record WHERE deal_id = 'step11-publish'; "
        "DELETE FROM flag WHERE deal_id = 'step11-publish'; "
        "DELETE FROM reconciliation WHERE deal_id = 'step11-publish'; "
        "DELETE FROM source_location WHERE doc_id IN (SELECT doc_id FROM document WHERE deal_id = 'step11-publish'); "
        "DELETE FROM fact WHERE deal_id = 'step11-publish'; "
        "DELETE FROM document WHERE deal_id = 'step11-publish'; "
        "DELETE FROM deal WHERE deal_id = 'step11-publish';",
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
        f"VALUES ('doc-step11', '{_DEAL}', '{version}', 'accounts.xlsx', 'xlsx', 'FIN_MGMT_ACCOUNTS', 'READ', 'B'); "
        "INSERT INTO source_location (location_id, doc_id, sheet_or_page, cell_range, value_as_read, extraction_method) "
        "VALUES ('loc-step11', 'doc-step11', 'PL', 'B2', '10', 'STATEMENT_READER'); "
        "INSERT INTO fact (fact_id, deal_id, entity_id, ontology_version, concept_id, value, unit_type, currency, "
        "period_type, period_start, period_end, months_covered, basis, dimensions, status, evidence_tier, source_location_ids, derived_from) "
        f"VALUES ('fact-step11-revenue', '{_DEAL}', 'CONSOLIDATED', '{version}', 'fin.pl.revenue', 10, 'CURRENCY', 'USD', "
        "'FY', DATE '2025-01-01', DATE '2025-12-31', 12, 'ACTUAL', '{}'::jsonb, 'SELECTED', 'B', ARRAY['loc-step11'], ARRAY[]::text[]); "
        "INSERT INTO fact (fact_id, deal_id, entity_id, ontology_version, concept_id, value, unit_type, currency, "
        "period_type, period_start, period_end, months_covered, basis, dimensions, status, evidence_tier, source_location_ids, derived_from) "
        f"VALUES ('fact-step11-da', '{_DEAL}', 'CONSOLIDATED', '{version}', 'fin.pl.da', 1, 'CURRENCY', 'USD', "
        "'FY', DATE '2025-01-01', DATE '2025-12-31', 12, 'ACTUAL', '{}'::jsonb, 'DERIVED', 'B', ARRAY[]::text[], ARRAY['fact-step11-revenue']);",
    )
