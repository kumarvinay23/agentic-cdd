"""A confirmed profile writes the deal row, and data ingestion reads statement cells."""

import datetime as dt
import os
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from agetic_cdd_api.services_deal_profile import confirm_profile, published_databook
from agetic_cdd_api.services_library import ingest_phase1
from agetic_cdd_api.services_statement_reader import read_confirmed_room

_DEAL = "workflow-read"
_MONTHS = [
    dt.datetime(2025, 1, 31),
    dt.datetime(2025, 2, 28),
    dt.datetime(2025, 3, 31),
    dt.datetime(2025, 4, 30),
    dt.datetime(2025, 5, 31),
    dt.datetime(2025, 6, 30),
]


def test_data_ingestion_reads_the_confirmed_room(tmp_path, monkeypatch) -> None:
    seen: dict[str, str] = {}
    monkeypatch.setattr("agetic_cdd_api.services_library.ingest_vdr_to_library", lambda db, deal: {})
    monkeypatch.setattr(
        "agetic_cdd_api.services_library.phase1_agent_output",
        lambda deal, agent_key, index: {"status": "completed"},
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_statement_reader.read_confirmed_room",
        lambda deal: seen.setdefault("deal_id", deal.id),
    )
    ingest_phase1(None, deal=SimpleNamespace(id=_DEAL, slug=_DEAL))
    assert seen["deal_id"] == _DEAL


def test_confirm_writes_the_deal_and_the_room_read_stores_cells(tmp_path, monkeypatch) -> None:
    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("databook URL is not set")
    monkeypatch.setattr("agetic_cdd_api.services_deals.deals_root", lambda: tmp_path)
    _clear(url)
    deal = SimpleNamespace(id=_DEAL, slug=_DEAL)
    docs = tmp_path / _DEAL / "documents"
    docs.mkdir(parents=True)
    _workbook(docs / "statement.xlsx")
    confirm_profile(deal, {
        "country": "United States",
        "currency": "USD",
        "sector": "saas",
        "business_model": "services",
        "deal_type": "buyout",
        "fiscal_year_end": "12-31",
        "latest_actual_month": "2025-06",
        "sector_pack": "payments",
        "ebitda_policy": {
            "include_other_operating_income": False,
            "rent_basis": "GAAP",
            "bad_debt_in_ebitda": False,
        },
    })
    from agetic_cdd_api.services_deal_profile import _PUBLISHED

    _PUBLISHED.pop(_DEAL, None)
    published = published_databook(_DEAL)
    assert published["reporting_currency"] == "USD"
    assert published["fiscal_year_end"] == "12-31"
    assert published["latest_actual_month"] == "2025-06-30"
    assert published["sector_packs"] == ["payments"]
    read_confirmed_room(deal)
    from agetic_cdd_api.services_databook_migrate import psql

    viewed = psql(
        url,
        "SELECT concept_id, cell_range FROM v_databook_fact "
        f"WHERE deal_id = '{_DEAL}' AND concept_id = 'fin.pl.revenue' AND cell_range IS NOT NULL;",
    )
    assert "fin.pl.revenue" in viewed.stdout
    assert "B2" in viewed.stdout


def _clear(url: str) -> None:
    from agetic_cdd_api.services_databook_migrate import psql

    psql(
        url,
        "DELETE FROM reconciliation WHERE deal_id = 'workflow-read'; "
        "DELETE FROM flag WHERE deal_id = 'workflow-read'; "
        "DELETE FROM record WHERE deal_id = 'workflow-read'; "
        "DELETE FROM mapping_decision WHERE deal_id = 'workflow-read'; "
        "DELETE FROM source_location WHERE doc_id IN (SELECT doc_id FROM document WHERE deal_id = 'workflow-read'); "
        "DELETE FROM fact WHERE deal_id = 'workflow-read'; "
        "DELETE FROM document WHERE deal_id = 'workflow-read'; "
        "DELETE FROM deal WHERE deal_id = 'workflow-read';",
    )


def _workbook(path) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "PL"
    for index, month in enumerate(_MONTHS, start=2):
        sheet.cell(1, index, month)
    sheet["A2"] = "Revenue"
    for index, value in enumerate([10, 11, 12, 13, 14, 15], start=2):
        sheet.cell(2, index, value)
    sheet["A3"] = "Gross profit"
    for index, value in enumerate([4, 4, 5, 5, 6, 6], start=2):
        sheet.cell(3, index, value)
    book.save(path)
