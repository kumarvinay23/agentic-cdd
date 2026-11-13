"""One chosen value per figure. The other document stays visible."""

from agetic_cdd_api.services_fact_repository import get_fact, save_fact
from agetic_cdd_api.services_resolver import resolve_fact


def test_a_second_document_stays_visible_without_a_duplicate_choice() -> None:
    first = _row("fact-step9-cim", 12, "CIM", "2024-06-30")
    second = _row("fact-step9-audited", 10, "FIN_AUDITED_FS", "2024-06-30")
    save_fact(resolve_fact(first))
    save_fact(resolve_fact(second))

    chosen = get_fact("fact-step9-audited")
    other = get_fact("fact-step9-cim")
    assert chosen["status"] == "SELECTED"
    assert chosen["value"] == 10
    assert other["status"] == "COMPARATIVE"
    assert other["reason_code"] == "LOWER_AUTHORITY"
    assert other["value"] == 12


def test_a_monthly_figure_uses_the_monthly_authority_order() -> None:
    audited = _row("fact-step9-month-audited", 4, "FIN_AUDITED_FS", "2024-06-30", period_type="FM", months_covered=1)
    accounts = _row("fact-step9-month-accounts", 5, "FIN_MGMT_ACCOUNTS", "2024-06-30", period_type="FM", months_covered=1)
    save_fact(resolve_fact(audited))
    save_fact(resolve_fact(accounts))

    assert get_fact("fact-step9-month-accounts")["status"] == "SELECTED"
    assert get_fact("fact-step9-month-accounts")["value"] == 5
    assert get_fact("fact-step9-month-audited")["status"] == "COMPARATIVE"
    assert get_fact("fact-step9-month-audited")["value"] == 4


def _row(fact_id: str, value: float, doc_type: str, period_end: str, **overrides: object) -> dict:
    row = {
        "fact_id": fact_id,
        "deal_id": "step9-resolve",
        "doc_id": f"doc-{fact_id}",
        "doc_type": doc_type,
        "concept_id": "fin.pl.revenue_gross",
        "value": value,
        "unit_type": "CURRENCY",
        "currency": "USD",
        "period_type": "FY",
        "period_start": "2024-01-01",
        "period_end": period_end,
        "months_covered": 12,
        "basis": "ACTUAL",
        "status": "SELECTED",
        "evidence_tier": "A",
        "source_location_ids": [f"loc-{fact_id}"],
        "dimensions": {},
    }
    row.update(overrides)
    return row
