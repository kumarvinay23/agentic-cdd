"""The ontology bundle is loaded once, and every fact row carries its version."""

import os
from pathlib import Path

import pytest

from agetic_cdd_api.services_databook_migrate import psql
from agetic_cdd_api.services_fact_repository import get_fact, save_fact
from agetic_cdd_api.services_ontology import _BUNDLE, insert_deal, load_ontology, stamp

_URL = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
_DEAL = "step2-stamp"


def test_bundle_loads_once_and_is_not_written() -> None:
    before = Path(_BUNDLE).read_bytes()
    first = load_ontology()
    second = load_ontology(str(_BUNDLE))
    assert first is second
    assert first.version
    assert "fin.pl.revenue_gross" in first.concepts
    assert first.candidates("Gross revenue", {"PL"})[0][0] == "fin.pl.revenue_gross"
    assert Path(_BUNDLE).read_bytes() == before
    source = Path(load_ontology.__globals__["__file__"]).read_text()
    assert "write_text" not in source
    assert '"w"' not in source and "'w'" not in source


def test_stamp_replaces_a_caller_version() -> None:
    stamped = stamp({"ontology_version": "0.0.0", "deal_id": _DEAL})
    assert stamped["ontology_version"] == load_ontology().version
    assert stamped["ontology_version"] != "0.0.0"


@pytest.mark.skipif(not _URL, reason="AGETIC_CDD_DATABOOK_DATABASE_URL is not set")
def test_every_fact_row_carries_the_loaded_version() -> None:
    version = load_ontology().version
    psql(_URL, f"DELETE FROM fact WHERE deal_id = '{_DEAL}'; DELETE FROM deal WHERE deal_id = '{_DEAL}';")
    insert_deal(
        _URL,
        {
            "deal_id": _DEAL,
            "ontology_version": "0.0.0",
            "reporting_currency": "USD",
            "fiscal_year_end": "12-31",
            "latest_actual_month": "2025-12-31",
        },
    )
    save_fact(
        {
            "fact_id": "fact-step2",
            "deal_id": _DEAL,
            "ontology_version": "0.0.0",
            "concept_id": "fin.pl.revenue_gross",
            "value": 1,
            "unit_type": "CURRENCY",
            "currency": "USD",
            "period_type": "FY",
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "months_covered": 12,
            "fiscal_year": 2025,
            "basis": "ACTUAL",
            "status": "SELECTED",
            "evidence_tier": "A",
            "source_location_ids": ["loc-step2"],
        },
    )
    assert get_fact("fact-step2")["ontology_version"] == version
    stored = psql(_URL, f"SELECT ontology_version FROM fact WHERE fact_id = 'fact-step2';")
    assert stored.returncode == 0
    assert version in stored.stdout
    missing = psql(
        _URL,
        "SELECT count(*) FROM fact WHERE ontology_version IS NULL "
        f"OR ontology_version <> '{version}';",
    )
    assert missing.returncode == 0
    counts = [line.strip() for line in missing.stdout.splitlines() if line.strip().isdigit()]
    assert counts == ["0"]
