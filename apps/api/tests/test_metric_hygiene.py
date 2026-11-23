"""Unit/scale hygiene — earnings bases and Ops grid scale quarantine."""

from __future__ import annotations


def test_clean_money_unit_collapses_joins() -> None:
    from agetic_cdd_api.services_metric_hygiene import clean_money_unit

    assert clean_money_unit("USD | USD M") == "USD M"
    assert clean_money_unit("USD M | M") == "USD M"
    assert clean_money_unit("USD B") == "USD B"
    assert clean_money_unit("") == "USD M"


def test_earnings_basis_rejects_zero_and_noise() -> None:
    from agetic_cdd_api.services_metric_hygiene import (
        earnings_basis_is_usable,
        sanitize_earnings_basis,
    )

    assert not earnings_basis_is_usable({"amount": 0.0, "unit": "USD M"})
    assert not earnings_basis_is_usable({"amount": "Revenue 0.0 USD | USD M"})
    cleaned = sanitize_earnings_basis(
        {"metric": "Revenue", "amount": 0.0, "unit": "USD | USD M", "period": "FY2025E"}
    )
    assert cleaned.get("amount") is None
    assert cleaned.get("unit") == "USD M"
    assert earnings_basis_is_usable(
        {"metric": "Revenue", "amount": 13.282, "unit": "USD M"}
    )


def test_earnings_basis_skips_zero_historical_pl() -> None:
    from agetic_cdd_api.agent_document_valuation_modeling import _earnings_basis

    earn = _earnings_basis(
        company="Compost Crew",
        corpus="No pack USD revenue figure here.",
        legacy={},
        trading_comps=None,
        historical={
            "pl_lines": [
                {
                    "line_item": "Revenue",
                    "unit": "USD | USD M",
                    "fy2025_value": 0.0,
                    "fy2024_value": 11.741,
                    "fy2023_value": 7.528,
                }
            ]
        },
    )
    assert float(earn["amount"]) == 11.741
    assert earn["unit"] == "USD M"
    assert "FY2024" in str(earn.get("period") or "")


def test_polluted_insight_filters_meta_and_zero_earnings() -> None:
    from agetic_cdd_api.services_metric_hygiene import (
        filter_insight_lines,
        is_polluted_insight,
        scrub_insight_text,
    )

    assert is_polluted_insight("Quality PASS · Reliance BLOCKED")
    assert is_polluted_insight("QA 2/8 PASS")
    assert is_polluted_insight("Databook promoted · 30 P&L line(s)")
    assert is_polluted_insight(
        "Earnings basis: Revenue 0.0 USD | USD M (FY2025E (accounts))"
    )
    assert is_polluted_insight(
        "Earnings (registered): Earnings basis: Revenue 0.0 USD | USD M (FY2025E)."
    )
    assert not is_polluted_insight(
        "EBITDA was already positive in FY2024 (USD M 1.135); FY2025 is USD M 0.572."
    )
    assert not is_polluted_insight("Municipal concentration is 22.9% of FY25 revenue.")

    # Trailing QA chrome is stripped; useful prose is kept.
    scrubbed = scrub_insight_text(
        "Revenue FY2025 +13% YoY (same-basis). (Quality PASS · Reliance READY)"
    )
    assert "Quality PASS" not in scrubbed
    assert "13%" in scrubbed
    assert not is_polluted_insight(scrubbed)

    kept = filter_insight_lines(
        [
            "Quality PASS · Reliance READY",
            "Revenue growth slowed to 13% in FY2025.",
            "Revenue 0.0 USD | USD M",
            "Core residential revenue declining YTD.",
            "ARR grew on municipal contracts. (Quality PASS · Reliance LIMITED)",
        ],
        limit=5,
    )
    assert kept == [
        "Revenue growth slowed to 13% in FY2025.",
        "Core residential revenue declining YTD.",
        "ARR grew on municipal contracts.",
    ]


def test_quarantine_released_pl_scale_outliers() -> None:
    from agetic_cdd_api.services_metric_hygiene import quarantine_pl_line_scale

    lines = quarantine_pl_line_scale(
        [
            {
                "line_item": "EBITDA",
                "metric_key": "ebitda",
                "unit": "USD M | USD",
                "fy2024_value": 1.115,
                "fy2025_value": 98097.67,
                "fy2026_value": 68082.49,
                "fy2027_value": 0.325,
            },
            {
                "line_item": "Revenue",
                "metric_key": "revenue",
                "unit": "USD M",
                "fy2023_value": 53876.28,
                "fy2026_value": 14.3,
            },
        ]
    )
    ebitda = next(l for l in lines if l["metric_key"] == "ebitda")
    revenue = next(l for l in lines if l["metric_key"] == "revenue")
    assert "fy2025_value" not in ebitda
    assert "fy2026_value" not in ebitda
    assert ebitda["fy2024_value"] == 1.115
    assert ebitda["fy2027_value"] == 0.325
    assert "fy2023_value" not in revenue
    assert revenue["fy2026_value"] == 14.3


def test_earnings_basis_prefers_scale_consistent_revenue() -> None:
    from agetic_cdd_api.agent_document_valuation_modeling import _earnings_basis

    earn = _earnings_basis(
        company="Compost Crew",
        corpus="No pack USD revenue figure here.",
        legacy={},
        trading_comps=None,
        historical={
            "pl_lines": [
                {
                    "line_item": "Revenue",
                    "unit": "USD M",
                    "fy2025_value": 0.0,
                    "fy2024_value": 13.282,
                    "fy2023_value": 53876.28,
                }
            ]
        },
    )
    assert float(earn["amount"]) == 13.282
    assert "FY2024" in str(earn.get("period") or "")
    assert earn["unit"] == "USD M"


def test_ops_grid_quarantines_raw_dollar_next_to_usd_m() -> None:
    from agetic_cdd_api.report_ops_dashboard import (
        MetricFact,
        build_year_metric_grid,
        derive_kpi_scorecard,
        sanitize_metric_facts_scale,
    )

    facts = [
        MetricFact(
            family="cash",
            label="Cash",
            value=2.754,
            year=2025,
            agent_key="databook",
            agent_name="Databook",
            unit="USD M",
        ),
        MetricFact(
            family="cash",
            label="Cash",
            value=2753840.63,
            year=2025,
            agent_key="historical_performance",
            agent_name="Historical",
            unit="USD",
        ),
        # Polluted *released* EBITDA must lose to scale-consistent peers.
        MetricFact(
            family="ebitda",
            label="EBITDA",
            value=98097.67,
            year=2025,
            agent_key="databook",
            agent_name="Databook",
            unit="USD",
        ),
        MetricFact(
            family="ebitda",
            label="EBITDA",
            value=0.572,
            year=2025,
            agent_key="historical_performance",
            agent_name="Historical",
            unit="USD M",
        ),
        MetricFact(
            family="ebitda",
            label="EBITDA",
            value=1.115,
            year=2024,
            agent_key="databook",
            agent_name="Databook",
            unit="USD M",
        ),
        MetricFact(
            family="revenue",
            label="Revenue",
            value=13.282,
            year=2025,
            agent_key="databook",
            agent_name="Databook",
            unit="USD M",
        ),
        MetricFact(
            family="revenue",
            label="Revenue",
            value=11.741,
            year=2024,
            agent_key="databook",
            agent_name="Databook",
            unit="USD M",
        ),
        MetricFact(
            family="revenue",
            label="Revenue",
            value=0.0,
            year=2025,
            agent_key="historical_performance",
            agent_name="Historical",
            unit="USD M",
        ),
        MetricFact(
            family="gross_margin",
            label="Gross Margin",
            value=0.304388,
            year=2025,
            agent_key="databook",
            agent_name="Databook",
            unit="%",
        ),
    ]
    clean = sanitize_metric_facts_scale(facts)
    assert all(not (f.family == "cash" and abs(f.value) > 1000) for f in clean)
    assert all(not (f.family == "ebitda" and abs(f.value) > 1000) for f in clean)
    assert all(
        not (f.family == "revenue" and f.value == 0.0 and f.agent_key != "databook")
        for f in clean
    )

    years, rows = build_year_metric_grid(facts)
    by_label = {label: series for label, series in rows}
    assert 2025 in years
    assert abs(by_label["Cash"][2025] - 2.754) < 1e-9
    assert abs(by_label["EBITDA"][2025] - 0.572) < 1e-9
    assert abs(by_label["Revenue"][2025] - 13.282) < 1e-9

    kpis = {k.name: k for k in derive_kpi_scorecard(facts, [])}
    assert "13.0%" in str(kpis["Revenue Growth (YoY)"].yoy) or "13.1%" in str(
        kpis["Revenue Growth (YoY)"].yoy
    )
    assert "98097" not in str(kpis["EBITDA"].latest)
    assert "0.572" in str(kpis["EBITDA"].latest) or "0.57" in str(kpis["EBITDA"].latest)
    assert "30.4" in str(kpis["Gross Margin"].latest)
