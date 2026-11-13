"""Only the fact repository writes a fact, and the other fixes read it back."""

from pathlib import Path

import pytest

from agetic_cdd_api.services_agent_result import note_fact
from agetic_cdd_api.services_calculation_library import ask_calculation
from agetic_cdd_api.services_claims import select_by_authority
from agetic_cdd_api.services_fact_repository import get_fact, save_fact, update_fact
from agetic_cdd_api.services_report_check import review
from agetic_cdd_api.services_verification import _recompute_gap


def test_only_the_repository_inserts_a_fact() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "agetic_cdd_api"
    writers = [path.name for path in root.glob("*.py") if "INSERT INTO fact" in path.read_text()]
    assert writers == ["services_fact_repository.py"]


def test_contract_and_schema_refuse_a_bad_fact() -> None:
    with pytest.raises(ValueError, match="FY"):
        save_fact(_row(period_type="FY", months_covered=7))
    with pytest.raises(ValueError, match="currency"):
        save_fact(_row(unit_type="CURRENCY", currency=None))
    with pytest.raises(ValueError, match="schema"):
        save_fact(_row(concept_id="missing.concept"))


def test_a_second_chosen_value_is_refused() -> None:
    first = dict(_row(), fact_id="fact-chosen-a", period_end="2024-12-31")
    save_fact(first)
    with pytest.raises(ValueError, match="fact_key_selected"):
        save_fact(dict(first, fact_id="fact-chosen-b"))


def test_calculation_claim_and_report_use_the_repository() -> None:
    calculated = ask_calculation(
        "CALC-KPI-GRR",
        inputs={"opening_revenue": 10000, "contraction": 1000, "churn": 273},
        sources=["ledger"],
    )
    assert calculated["fact_id"].startswith("fact-")
    assert get_fact(calculated["fact_id"])["concept_id"] == "kpi.grr_pct"
    assert get_fact(calculated["fact_id"])["value"] == calculated["value"]

    comps = ask_calculation("CALC-COMPS-MEDIAN", inputs={"multiples": [6, 8, 10, 11]})
    assert "fact_id" not in comps

    store: dict = {}
    fact_id = note_fact(
        store,
        name="grr",
        source="ledger",
        calc_id="CALC-KPI-GRR",
        inputs={"opening_revenue": 10000, "contraction": 1000, "churn": 273},
    )
    assert fact_id.startswith("fact-")
    assert store[fact_id]["value"] == 0.8727
    assert get_fact(fact_id)["value"] == 0.8727
    update_fact(fact_id, {"value": 0.5})
    assert _recompute_gap(get_fact(fact_id) | {"calc_id": "CALC-KPI-GRR", "rounding": 4, "value": 0.8727})

    chosen, conflicts = select_by_authority(
        "FINANCIAL_ACTUAL",
        [{"doc_type": "CIM", "value": 9}, {"doc_type": "FIN_AUDITED_FS", "value": 8}],
    )
    assert chosen["fact_id"].startswith("fact-")
    assert get_fact(chosen["fact_id"])["conflicts"] == conflicts

    cited = save_fact(_row(fact_id="fact-cited", value=8, period_end="2023-12-31"))
    report = {"pages": [{"page_id": "P1", "title": "1. Revenue was 8.", "body": "", "fact_id": cited}], "executive_summary": {"title": "", "body": ""}}
    checked = review(report, [])
    assert all("not in the fact store" not in error for error in checked["errors"])

    update_fact(cited, {"value": 9})
    assert get_fact(cited)["value"] == 9


def _row(**overrides: object) -> dict:
    row = {
        "deal_id": "step3-repo",
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
        "source_location_ids": ["loc-step3"],
    }
    row.update(overrides)
    return row
