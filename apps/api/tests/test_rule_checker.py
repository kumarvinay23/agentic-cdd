"""A failing block rule is an open flag, and its tab stays unpublished."""

import os

from agetic_cdd_api.services_fact_repository import Fact
from agetic_cdd_api.services_rule_checker import check_rules

_DEAL = "step10-rules"


def test_a_failing_rule_is_open_and_its_tab_is_not_published() -> None:
    _clear_deal()
    facts = [
        _fact("fin.pl.revenue", 10, "fact-step10-revenue"),
        _fact("fin.pl.cost_of_sales", 4, "fact-step10-cost"),
        _fact("fin.pl.gross_profit", 10, "fact-step10-gross"),
        _fact("fin.pl.ebitda", 20, "fact-step10-mgmt", {"view": "MANAGEMENT"}),
        _fact("fin.pl.ebitda", 10, "fact-step10-reported", {"view": "REPORTED"}),
    ]
    checked = check_rules(facts, _DEAL)
    codes = {flag["code"] for flag in checked["flags"]}
    assert "R-PL-02" in codes
    assert "R-QOE-01" in codes
    assert all(flag["severity"] == "block" and flag["status"] == "OPEN" for flag in checked["flags"] if flag["code"] in codes)
    assert "FDD-06" not in checked["publish_set"]
    assert "FDD-07" in checked["publish_set"]

    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        return
    from agetic_cdd_api.services_databook_migrate import psql

    stored = psql(url, f"SELECT code FROM v_open_flags WHERE deal_id = '{_DEAL}';")
    assert "R-PL-02" in stored.stdout
    assert "R-QOE-01" in stored.stdout


def _fact(concept: str, value: float, fact_id: str, dimensions: dict | None = None) -> Fact:
    return Fact(
        concept, value, "CURRENCY", "FY", "2025-01-01", "2025-12-31", 12, "ACTUAL",
        dimensions or {}, "doc-step10", "B", [f"loc-{fact_id}"], status="SELECTED", currency="USD", fact_id=fact_id,
    )


def _clear_deal() -> None:
    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        return
    from agetic_cdd_api.services_databook_migrate import psql
    from agetic_cdd_api.services_ontology import insert_deal

    psql(
        url,
        "DELETE FROM flag WHERE deal_id = 'step10-rules'; "
        "DELETE FROM reconciliation WHERE deal_id = 'step10-rules'; "
        "DELETE FROM fact WHERE deal_id = 'step10-rules'; "
        "DELETE FROM deal WHERE deal_id = 'step10-rules';",
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
