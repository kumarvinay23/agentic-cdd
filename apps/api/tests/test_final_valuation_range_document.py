"""Final Valuation Range — DiligenceIQ prompt-book committee band."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_final_valuation_range import (
    _heuristic_final_range_spec,
    _walk_away,
    build_final_valuation_range_spec,
    render_final_valuation_range_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.agent_document_valuation_modeling import (
    _heuristic_valuation_modeling_spec,
    render_valuation_modeling_markdown,
)
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-fvr-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _valuation() -> dict:
    return {
        "earnings_basis": {
            "metric": "Revenue",
            "period": "FY2024E",
            "amount": 590.0,
            "unit": "USD M",
            "source": "(DOC: data room financials)",
        },
        "comps_summary": {
            "median_multiple": 1.8,
            "range_multiple_low": 0.8,
            "range_multiple_high": 2.1,
            "implied_ev_usd_b_low": 0.47,
            "implied_ev_usd_b_high": 1.24,
        },
        "precedents_summary": {
            "median_multiple": 2.1,
            "implied_ev_usd_b_low": 1.0,
            "implied_ev_usd_b_high": 2.5,
        },
        "dcf": {
            "wacc_pct": 9.0,
            "enterprise_value_usd_b": 2.55,
            "scenarios": [
                {
                    "label": "Bear Case",
                    "enterprise_value_usd_b": 1.03,
                    "equity_value_per_share_inr": 14.9,
                },
                {
                    "label": "Base Case",
                    "enterprise_value_usd_b": 2.1,
                    "equity_value_per_share_inr": 34.9,
                },
                {
                    "label": "Bull Case",
                    "enterprise_value_usd_b": 4.87,
                    "equity_value_per_share_inr": 86.5,
                },
            ],
        },
        "sensitivity_analysis": {
            "scenario_cases": [
                {
                    "case": "Bear Case",
                    "growth_assumption": "Revenue CAGR 22%; terminal growth 1.5%",
                    "margin_assumption": "EBITDA margin 6%",
                    "capital_assumption": "WACC 11.5%",
                },
                {
                    "case": "Base Case",
                    "growth_assumption": "Revenue CAGR 38%; terminal growth 3%",
                    "margin_assumption": "EBITDA margin 14%",
                    "capital_assumption": "WACC 9%",
                },
                {
                    "case": "Bull Case",
                    "growth_assumption": "Revenue CAGR 55%; terminal growth 4.5%",
                    "margin_assumption": "EBITDA margin 22%",
                    "capital_assumption": "WACC 7.5%",
                },
            ],
            "breakevens": [
                {
                    "operating_terms": "If WACC rises +100bp, terminal growth must reach ≥ 5%",
                }
            ],
        },
    }


def _capital_incomplete() -> dict:
    return {
        "schedule_complete": False,
        "schedule_gaps": ["Senior Term Loan A: missing lender, rate, maturity"],
        "debt_total_usd_m": 200.0,
        "debt_like_items": [{"item": "Lease", "amount": 22.0}],
        "cash_split": [
            {"bucket": "Freely available", "amount": "Information request: freely available"},
        ],
        "net_debt_bridge": [
            {"component": "Gross debt (scheduled facilities)", "amount": 200.0},
            {
                "component": "Net debt (completion funding position)",
                "amount": "Information request: net debt",
            },
        ],
    }


def _capital_complete() -> dict:
    return {
        "schedule_complete": True,
        "debt_total_usd_m": 240.0,
        "debt_like_items": [{"item": "Lease", "amount": 22.0}],
        "cash_split": [
            {"bucket": "Freely available", "amount": 40.0},
            {"bucket": "Restricted", "amount": 12.0},
            {"bucket": "Operating minimum", "amount": 15.0},
        ],
        "net_debt_bridge": [
            {"component": "Gross debt (scheduled facilities)", "amount": 240.0, "sign": "+"},
            {"component": "Less: freely available cash", "amount": 40.0, "sign": "−"},
            {"component": "Plus: debt-like items", "amount": 22.0, "sign": "+"},
            {"component": "Net debt (completion funding position)", "amount": 222.0, "sign": "="},
        ],
    }


def _revenue_quality_ok() -> dict:
    return {"quality_verdict": "PASS", "reliance_verdict": "READY"}


def test_final_range_prompt_book_listed() -> None:
    system = compose_system("final_valuation_range", sector="EV", geography="India")
    assert "final_valuation_range" in listed_agents()
    assert "walk" in system.lower() or "range" in system.lower()
    body = agent_prompt("final_valuation_range")
    assert "Ola" not in body and "SoftBank" not in body
    assert "synerg" in body.lower()
    assert "net debt" in body.lower()


def test_final_range_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_final_valuation_range.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"


def test_range_withheld_when_net_debt_incomplete() -> None:
    fvr = _heuristic_final_range_spec(
        company="Test3",
        corpus="Net Debt at Valuation Date (USD M) USD 240M. Working Capital Build 6%.",
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        valuation_spec=_valuation(),
        capital_structure=_capital_incomplete(),
        revenue_quality=_revenue_quality_ok(),
        sensitivity_analysis=_valuation()["sensitivity_analysis"],
    )
    assert fvr.get("range_published") is False
    assert fvr.get("ev_low_usd_b") is None
    blockers = fvr.get("blockers") or []
    assert any(
        isinstance(b, dict) and not b.get("ready") and "net debt" in str(b.get("name") or "").lower()
        for b in blockers
    )
    assert fvr.get("reliance_verdict") == "BLOCKED"
    # Triangulation still present for transparency
    pts = fvr.get("range_points") or {}
    assert pts.get("low") and pts.get("base") and pts.get("high")


def test_range_published_when_ready() -> None:
    fvr = _heuristic_final_range_spec(
        company="Test3",
        corpus="Working Capital Build (% of Revenue growth) 6%. No synergies.",
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        valuation_spec=_valuation(),
        capital_structure=_capital_complete(),
        revenue_quality=_revenue_quality_ok(),
        sensitivity_analysis=_valuation()["sensitivity_analysis"],
    )
    assert fvr.get("range_published") is True
    assert fvr.get("ev_low_usd_b") == 1.03
    assert fvr.get("ev_base_usd_b") == 2.1
    assert fvr.get("ev_high_usd_b") == 4.87
    # Implied multiples on declared earnings
    low = (fvr.get("range_points") or {}).get("low") or {}
    assert low.get("implied_multiple_x") is not None
    assert abs(float(low["implied_multiple_x"]) - (1.03 * 1000 / 590)) < 0.05
    # Assumption set named
    assert "CAGR" in str(low.get("assumption_set") or "") or "WACC" in str(
        low.get("assumption_set") or ""
    )
    # Equity bridge uses capital net debt
    bridge = fvr.get("equity_bridge") or []
    assert bridge
    assert bridge[0].get("bridge_status") == "ready"
    assert bridge[0].get("net_debt_usd_m") == 222.0
    # Walk-away above high
    walk = fvr.get("walk_away") or {}
    assert walk.get("above_recommended_high") is True
    assert float(walk["walk_away_enterprise_value_usd_b"]) > float(fvr["ev_high_usd_b"])
    # Stand-alone — no synergies credited
    stand = fvr.get("stand_alone") or {}
    assert stand.get("stand_alone_only") is True
    assert stand.get("synergies_credited") is False
    assert fvr.get("quality_verdict") == "PASS"
    assert fvr.get("reliance_verdict") == "READY"


def test_walk_away_must_be_above_high() -> None:
    range_pts = {
        "low": {"enterprise_value_usd_b": 1.0},
        "base": {"enterprise_value_usd_b": 2.0},
        "high": {"enterprise_value_usd_b": 3.0},
    }
    walk = _walk_away(range_pts=range_pts, sensitivity=None)
    assert walk["above_recommended_high"] is True
    assert walk["walk_away_enterprise_value_usd_b"] > 3.0


def test_render_no_invest_and_gate() -> None:
    fvr = _heuristic_final_range_spec(
        company="Test3",
        corpus="Working Capital 6%. We recommend invest.",
        sources=["13_Valuation.pdf"],
        valuation_spec=_valuation(),
        capital_structure=_capital_incomplete(),
        revenue_quality=_revenue_quality_ok(),
    )
    md = render_final_valuation_range_markdown("Final Valuation Range", fvr)
    assert "## 0. Publishing Gate" in md
    assert "WITHHELD" in md
    assert "## 1. Low / Base / High Enterprise Value" in md
    assert "## 3. Walk-away Price" in md
    assert "## 4. Stand-alone vs Buyer Synergies" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()


def test_valuation_document_embeds_final_range() -> None:
    val = _heuristic_valuation_modeling_spec(
        company="Test3",
        corpus="FY2024E Revenue USD 590M. WACC (Base) 9.0%.",
        sources=["13_Valuation.pdf"],
        legacy_spec={"dcf": _valuation()["dcf"], "fv_code": "FV-05"},
    )
    fvr = _heuristic_final_range_spec(
        company="Test3",
        corpus="Working Capital Build 6%.",
        sources=["13_Valuation.pdf"],
        valuation_spec={**val, **_valuation()},
        capital_structure=_capital_complete(),
        revenue_quality=_revenue_quality_ok(),
        sensitivity_analysis=_valuation()["sensitivity_analysis"],
    )
    val["final_valuation_range"] = fvr
    md = render_valuation_modeling_markdown("Valuation Model", val)
    assert "# Final Valuation Range" in md
    assert "## 0. Publishing Gate" in md


def test_render_agent_document_dispatch() -> None:
    val = _heuristic_valuation_modeling_spec(
        company="Test3",
        corpus="FY2024E Revenue USD 590M.",
        sources=["13_Valuation.pdf"],
        legacy_spec={"dcf": _valuation()["dcf"]},
    )
    val["final_valuation_range"] = _heuristic_final_range_spec(
        company="Test3",
        corpus="Working Capital 6%.",
        sources=["13_Valuation.pdf"],
        valuation_spec=_valuation(),
        capital_structure=_capital_incomplete(),
        revenue_quality=_revenue_quality_ok(),
    )
    md = render_agent_document(
        "valuation_modeling",
        {
            "agent_key": "valuation_modeling",
            "agentName": "Valuation Model",
            "target_company": "Test3",
            "sources": ["13_Valuation.pdf"],
            "spec": val,
        },
    )
    assert "# Final Valuation Range" in md or "## 1. Declared Earnings Basis" in md


def test_build_loads_capital_structure() -> None:
    deal = _FakeDeal()
    spec = build_final_valuation_range_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus="Working Capital Build 6%. Net Debt USD 240M.",
        sources=["13_Valuation.pdf"],
        valuation_spec=_valuation(),
        capital_structure=_capital_complete(),
        revenue_quality=_revenue_quality_ok(),
        prefer_heuristic=True,
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("range_published") is True
