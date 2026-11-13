"""The databook database refuses a bad fact before any report reads it."""

import os

import pytest

from agetic_cdd_api.services_databook_migrate import apply_databook_migrations, psql

_URL = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
_DEAL = "step1-constraints"
_CONCEPT = "fin.pl.revenue_gross"

pytestmark = pytest.mark.skipif(not _URL, reason="AGETIC_CDD_DATABOOK_DATABASE_URL is not set")


def setup_module() -> None:
    if not _URL:
        return
    apply_databook_migrations(_URL)
    _exec(
        f"DELETE FROM fact WHERE deal_id = '{_DEAL}';"
        f"DELETE FROM deal WHERE deal_id = '{_DEAL}';"
        "INSERT INTO deal (deal_id, ontology_version, reporting_currency, fiscal_year_end, latest_actual_month)"
        f" VALUES ('{_DEAL}', '1.0.0', 'USD', '12-31', DATE '2025-12-31');"
    )


def test_model_tables_and_views_exist() -> None:
    for name in (
        "onto_version",
        "onto_concept",
        "onto_dimension",
        "onto_document_type",
        "onto_authority",
        "onto_schedule",
        "onto_calculation",
        "onto_rule",
        "onto_reason_code",
        "onto_record_class",
        "deal",
        "document",
        "source_location",
        "dimension_member",
        "fact",
        "record",
        "reconciliation",
        "flag",
        "mapping_decision",
        "v_databook_fact",
        "v_open_flags",
    ):
        found = psql(_URL, f"SELECT to_regclass('public.{name}')")
        assert found.returncode == 0
        assert name in found.stdout


def test_a_valid_fy_fact_is_accepted() -> None:
    result = _fact("fact-ok", period_type="FY", months=12, currency="'USD'")
    assert result.returncode == 0, result.stderr


def test_seven_month_fy_is_refused_and_ytd_stays_partial() -> None:
    refused = _fact("fact-fy7", period_type="FY", months=7, currency="'USD'", end="2025-07-31")
    assert refused.returncode != 0
    assert "fy_is_12_months" in refused.stderr

    partial = _fact("fact-ytd12", period_type="YTD", months=12, currency="'USD'", end="2025-12-31")
    assert partial.returncode != 0
    assert "ytd_is_partial" in partial.stderr


def test_a_second_chosen_value_is_refused() -> None:
    first = _fact("fact-chosen", period_type="FY", months=12, currency="'USD'", end="2024-12-31", start="2024-01-01")
    assert first.returncode == 0, first.stderr
    second = _fact("fact-chosen-2", period_type="FY", months=12, currency="'USD'", end="2024-12-31", start="2024-01-01")
    assert second.returncode != 0
    assert "fact_key_selected" in second.stderr


def test_currency_amount_without_a_code_is_refused() -> None:
    result = _fact("fact-nocurrency", period_type="FQ", months=3, currency="NULL", end="2025-03-31", start="2025-01-01")
    assert result.returncode != 0
    assert "currency_needs_code" in result.stderr


def test_unknown_concept_is_refused() -> None:
    result = _fact(
        "fact-unknown",
        period_type="FQ",
        months=3,
        currency="'USD'",
        end="2025-06-30",
        start="2025-04-01",
        concept="missing.concept",
    )
    assert result.returncode != 0
    assert "onto_concept" in result.stderr


def _fact(
    fact_id: str,
    *,
    period_type: str,
    months: int,
    currency: str,
    end: str = "2025-12-31",
    start: str = "2025-01-01",
    concept: str = _CONCEPT,
) -> object:
    return _exec(
        "INSERT INTO fact ("
        "fact_id, deal_id, ontology_version, concept_id, value, unit_type, currency,"
        " period_type, period_start, period_end, months_covered, fiscal_year, basis,"
        " status, evidence_tier, source_location_ids"
        ") VALUES ("
        f"'{fact_id}', '{_DEAL}', '1.0.0', '{concept}', 1, 'CURRENCY', {currency},"
        f" '{period_type}', DATE '{start}', DATE '{end}', {months}, 2025, 'ACTUAL',"
        " 'SELECTED', 'A', ARRAY['loc-1']"
        ");"
    )


def _exec(sql: str):
    return psql(_URL, sql)
