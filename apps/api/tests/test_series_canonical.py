"""Gate 3 — one canonical Financial history series per metric × year."""

from __future__ import annotations

from agetic_cdd_api.services_fact_repository import get_fact, save_fact
from agetic_cdd_api.services_series_canonical import (
    canonicalize_financial_history,
    duplicate_metric_years,
)
from agetic_cdd_api.services_series_ingest import assess_statement_series_ingest


def test_cogs_alias_keeps_cost_of_sales() -> None:
    deal = "gate3-cogs"
    save_fact(
        _series_row(
            "fact-cogs-goods",
            deal,
            concept_id="fin.pl.cos.goods",
            value=40,
            doc_type="FIN_MGMT_ACCOUNTS",
        )
    )
    save_fact(
        _series_row(
            "fact-cogs-parent",
            deal,
            concept_id="fin.pl.cost_of_sales",
            value=42,
            doc_type="FIN_MGMT_ACCOUNTS",
        )
    )

    result = canonicalize_financial_history(deal)
    assert get_fact("fact-cogs-parent")["status"] == "SELECTED"
    assert get_fact("fact-cogs-goods")["status"] == "COMPARATIVE"
    assert any(item["fact_id"] == "fact-cogs-goods" for item in result["demoted"])
    assert duplicate_metric_years(deal_id=deal) == []


def test_higher_authority_doc_wins_revenue() -> None:
    deal = "gate3-revenue"
    # Distinct figure keys (dimensions) so the DB allows multiple SELECTED
    # rows that still collapse to one Financial history metric×year.
    save_fact(
        _series_row(
            "fact-rev-cim",
            deal,
            concept_id="fin.pl.revenue",
            value=100,
            doc_type="CIM",
            dimensions={"pack": "cim"},
        )
    )
    save_fact(
        _series_row(
            "fact-rev-audited",
            deal,
            concept_id="fin.pl.revenue",
            value=95,
            doc_type="FIN_AUDITED_FS",
            dimensions={"pack": "audit"},
        )
    )
    save_fact(
        _series_row(
            "fact-rev-mgmt",
            deal,
            concept_id="fin.pl.revenue",
            value=98,
            doc_type="FIN_MGMT_ACCOUNTS",
            dimensions={"pack": "mgmt"},
        )
    )

    result = canonicalize_financial_history(deal)
    assert get_fact("fact-rev-audited")["status"] == "SELECTED"
    assert get_fact("fact-rev-cim")["status"] == "COMPARATIVE"
    assert get_fact("fact-rev-mgmt")["status"] == "COMPARATIVE"
    assert len(result["demoted"]) >= 2
    assert duplicate_metric_years(deal_id=deal) == []


def test_fy_preferred_over_monthly_for_same_metric_year() -> None:
    deal = "gate3-period"
    save_fact(
        _series_row(
            "fact-rev-month",
            deal,
            concept_id="fin.pl.revenue",
            value=8,
            doc_type="FIN_MGMT_ACCOUNTS",
            period_type="FM",
            months_covered=1,
            period_start="2024-12-01",
            period_end="2024-12-31",
        )
    )
    save_fact(
        _series_row(
            "fact-rev-fy",
            deal,
            concept_id="fin.pl.revenue",
            value=96,
            doc_type="FIN_MGMT_ACCOUNTS",
            period_type="FY",
            months_covered=12,
            period_start="2024-01-01",
            period_end="2024-12-31",
        )
    )

    canonicalize_financial_history(deal)
    assert get_fact("fact-rev-fy")["status"] == "SELECTED"
    assert get_fact("fact-rev-month")["status"] == "COMPARATIVE"


def test_duplicate_detection_before_canonicalize() -> None:
    deal = "gate3-dupes"
    rows = [
        _series_row(
            "fact-dup-a",
            deal,
            concept_id="fin.pl.gross_profit",
            value=10,
            doc_type="FIN_MGMT_ACCOUNTS",
        ),
        _series_row(
            "fact-dup-b",
            deal,
            concept_id="fin.pl.gross_profit",
            value=11,
            doc_type="FIN_MGMT_ACCOUNTS",
            dimensions={"book": "mgmt"},
        ),
    ]
    for row in rows:
        save_fact(row)

    dupes = duplicate_metric_years(deal_id=deal)
    assert len(dupes) == 1
    assert dupes[0]["metric"] == "gross_profit"

    gate = assess_statement_series_ingest(
        type("D", (), {"id": deal, "slug": deal})(),
        {"facts": rows, "rows": []},
    )
    assert gate.ok is False
    assert any(r.startswith("multiple_canonical_series:") for r in gate.reasons)

    canonicalize_financial_history(deal)
    assert duplicate_metric_years(deal_id=deal) == []


def test_same_value_demoted_as_duplicate() -> None:
    deal = "gate3-same"
    save_fact(
        _series_row(
            "fact-same-a",
            deal,
            concept_id="fin.pl.ebitda",
            value=20,
            doc_type="FIN_AUDITED_FS",
        )
    )
    save_fact(
        _series_row(
            "fact-same-b",
            deal,
            concept_id="fin.pl.ebitda",
            value=20,
            doc_type="FIN_MGMT_ACCOUNTS",
            dimensions={"source": "bridge"},
        )
    )
    canonicalize_financial_history(deal)
    loser = get_fact("fact-same-b")
    assert loser["status"] == "COMPARATIVE"
    assert loser["reason_code"] == "DUPLICATE"


def _series_row(
    fact_id: str,
    deal_id: str,
    *,
    concept_id: str,
    value: float,
    doc_type: str,
    **overrides: object,
) -> dict:
    row = {
        "fact_id": fact_id,
        "deal_id": deal_id,
        "doc_id": f"doc-{fact_id}",
        "doc_type": doc_type,
        "concept_id": concept_id,
        "value": value,
        "unit_type": "CURRENCY",
        "currency": "USD",
        "period_type": "FY",
        "period_start": "2024-01-01",
        "period_end": "2024-12-31",
        "months_covered": 12,
        "basis": "ACTUAL",
        "status": "SELECTED",
        "evidence_tier": "A",
        "source_location_ids": [f"loc-{fact_id}"],
        "dimensions": {},
        "entity_id": "CONSOLIDATED",
    }
    row.update(overrides)
    return row
