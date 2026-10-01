"""Accounts-first P&L extract — QBO over CIM Crosswalk page numbers."""

from __future__ import annotations

from agetic_cdd_api.services_accounts_extract import (
    detect_unit_from_corpus,
    extract_accounts_pack,
    extract_qbo_monthly_annual_sums,
    extract_workbook_financial_summary,
    infer_sector_id_from_corpus,
    is_cim_crosswalk_context,
    is_placeholder_company,
    looks_like_cim_page_list,
    period_type_for_year,
    resolve_target_display_name,
)
from agetic_cdd_api.agent_document_historical_performance import (
    _extract_period_facts,
    _heuristic_historical_performance_spec,
)
from agetic_cdd_api.services_databook_map import map_caption


class _FakeDeal:
    id = "deal-accounts-1"
    slug = "test5"
    name = "Test5"
    company = "Test5"
    sector = "logistics"
    geography = "United States"


def test_cim_page_list_detected() -> None:
    assert looks_like_cim_page_list([2023.0, 8.0, 34.0, 60.0, 7.5])
    assert looks_like_cim_page_list([8.0, 34.0, 60.0])
    assert not looks_like_cim_page_list([7.528, 11.741, 13.282])


def test_cim_crosswalk_context() -> None:
    text = "Revenue 2023 CIM page(s) 8, 34, 60 $7.5mn Financial Summary"
    pos = text.index("8, 34")
    assert is_cim_crosswalk_context(text, pos)


def test_period_type_plan_years() -> None:
    assert period_type_for_year(2023) == "actual"
    assert period_type_for_year(2026) == "forecast"
    assert period_type_for_year(2025, header="2025P") == "forecast"


def test_detect_usd_from_corpus() -> None:
    unit, cur = detect_unit_from_corpus("Financial Summary ($M) Revenue 7.5")
    assert cur == "USD"
    assert "USD" in unit
    unit2, cur2 = detect_unit_from_corpus("Profit & Loss Summary (INR Crore)")
    assert cur2 == "INR"


def test_map_caption_skips_crosswalk_and_maps_total_revenues() -> None:
    assert map_caption("CIM page(s)") is None
    assert map_caption("Total Revenues") is not None
    assert map_caption("Total Revenues").metric_key == "revenue"
    assert map_caption("Gross Profit").metric_key == "gross_profit"


def test_sector_prefers_organics_over_logistics_hauling() -> None:
    corpus = (
        "Compost Crew organics collection and composting. "
        "Market sizing sheet: Logistics (Hauling) 1,661,465 homes."
    )
    assert infer_sector_id_from_corpus(corpus) == "waste_organics"


def test_placeholder_company() -> None:
    assert is_placeholder_company("Test5", "test5")
    assert not is_placeholder_company("Compost Crew", "test5")


def test_regex_rejects_cim_page_revenue() -> None:
    corpus = (
        "CIM Crosswalk Every figure traced. "
        "Revenue 2023 8, 34, 60 $7.5mn $7.528mn Financial Summary "
        "Gross Profit 1.539 3.718 3.952 4.639"
    )
    facts = _extract_period_facts(corpus)
    rev_vals = [
        f.get("value") for f in facts
        if str(f.get("line_item") or "").lower() == "revenue"
    ]
    assert 34.0 not in rev_vals
    assert 60.0 not in rev_vals
    assert 8.0 not in rev_vals


def test_qbo_and_workbook_extract_on_test5_if_present() -> None:
    """Integration: uses on-disk Test5 documents when available."""
    from pathlib import Path
    from types import SimpleNamespace

    docs = Path("data/deals/test5/documents")
    if not docs.is_dir():
        return
    # Minimal deal stub pointed at test5 folder via slug
    deal = SimpleNamespace(
        id="6d378356fb0878671b5bc7b1",
        slug="test5",
        name="Test5",
        company="Test5",
        sector="logistics",
        geography="United States",
    )
    qbo = extract_qbo_monthly_annual_sums(deal)  # type: ignore[arg-type]
    assert qbo is not None, "QBO Monthly P&L should parse"
    rev = (qbo.get("lines") or {}).get("Revenue") or {}
    assert abs(rev.get(2023, 0) - 7.558) < 0.05
    assert abs(rev.get(2024, 0) - 11.869) < 0.05
    ebitda = (qbo.get("lines") or {}).get("EBITDA") or {}
    assert ebitda.get(2023, 0) < 0  # loss
    assert ebitda.get(2024, 0) > 0
    assert qbo.get("unit") == "USD M"

    wb = extract_workbook_financial_summary(deal)  # type: ignore[arg-type]
    assert wb is not None
    assert 2026 in ((wb.get("lines") or {}).get("Revenue") or {})

    merged = extract_accounts_pack(deal)  # type: ignore[arg-type]
    assert merged is not None
    heur = _heuristic_historical_performance_spec(
        company="Compost Crew",
        corpus="CIM Crosswalk Revenue 2023 8, 34, 60 $7.5mn",
        sources=[],
        deal=deal,  # type: ignore[arg-type]
    )
    assert heur.get("accounts_extract") is True
    assert heur.get("reporting_unit") == "USD M"
    pl = {r["line_item"]: r for r in (heur.get("pl_lines") or []) if isinstance(r, dict)}
    assert "Revenue" in pl
    assert abs(float(pl["Revenue"]["fy2023_value"]) - 7.558) < 0.05
    assert abs(float(pl["Revenue"]["fy2024_value"]) - 11.869) < 0.05
    assert pl["Revenue"]["unit"] == "USD M"
    assert "INR" not in str(heur.get("trend_headline") or "")
    plan_facts = [
        f for f in (heur.get("period_facts") or [])
        if isinstance(f, dict) and f.get("period_type") == "forecast"
    ]
    assert plan_facts
    target = resolve_target_display_name(deal)  # type: ignore[arg-type]
    # Slug placeholder alone is not preferred when no CIM name available
    assert is_placeholder_company("Test5", "test5")
    assert target  # non-empty