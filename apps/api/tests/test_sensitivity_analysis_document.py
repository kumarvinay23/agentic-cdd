"""Sensitivity Analysis — DiligenceIQ prompt-book value drivers & break-evens."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.agent_document_sensitivity_analysis import (
    _check_returns,
    _direction_check,
    _heuristic_sensitivity_spec,
    _parse_grid,
    build_sensitivity_analysis_spec,
    render_sensitivity_analysis_markdown,
)
from agetic_cdd_api.agent_document_valuation_modeling import (
    _heuristic_valuation_modeling_spec,
    render_valuation_modeling_markdown,
)
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-sens-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _sens_corpus() -> str:
    return (
        "C2. Valuation Sensitivity Matrix (WACC vs. Terminal Growth Rate). "
        "The base case (9.0% WACC, 3.0% terminal growth) is highlighted. "
        "Enterprise Value Sensitivity (INR Crore) — WACC vs Terminal Growth "
        "WACC \\ Term. Growth 1.0% 2.0% 3.0% (Base) 4.0% 5.0% "
        "7.0% 22840 26120 30580 37200 48640 "
        "7.5% 20180 22840 26440 31620 39880 "
        "8.0% 17920 20040 22920 26960 33000 "
        "8.5% 16020 17720 20040 23200 27880 "
        "9.0% (Base) 14420 15760 17560 20040 23680 "
        "9.5% 13040 14140 15600 17520 20400 "
        "10.0% 11840 12760 13960 15520 17840 "
        "10.5% 10800 11580 12560 13840 15720 "
        "11.0% 9880 10540 11360 12400 13960 "
        "11.5% 9080 9640 10320 11200 12520 "
        "IPO price is only justified at WACC ≤ 7.5% with terminal growth ≥ 4.5%. "
        "Bear Case (WACC 11.5%, TG 1.5%) 8600 1.03B INR 14.9 -80.4% vs IPO Execution failure; subsidy cut "
        "Base Case (WACC 9.0%, TG 3.0%) 17560 2.10B INR 34.9 -54.1% vs IPO Moderate growth; service improvement "
        "Bull Case (WACC 7.5%, TG 4.5%) 40600 4.87B INR 86.5 13.8% vs IPO Optimistic FCF path "
        "Revenue CAGR 38%. Retention Rate (12M) 71%."
    )


def _valuation_legacy() -> dict:
    return {
        "dcf": {
            "wacc_pct": 9.0,
            "enterprise_value_usd_b": 2.55,
            "implied_share_price_inr": 43.1,
            "scenarios": [
                {
                    "label": "Bear Case",
                    "enterprise_value_usd_b": 1.03,
                    "equity_value_per_share_inr": 14.9,
                    "premium_discount_vs_ipo_pct": -80.4,
                },
                {
                    "label": "Base Case",
                    "enterprise_value_usd_b": 2.1,
                    "equity_value_per_share_inr": 34.9,
                    "premium_discount_vs_ipo_pct": -54.1,
                },
                {
                    "label": "Bull Case",
                    "enterprise_value_usd_b": 4.87,
                    "equity_value_per_share_inr": 86.5,
                    "premium_discount_vs_ipo_pct": 13.8,
                },
            ],
        },
        "fv_code": "FV-05",
    }


def _recommendation() -> dict:
    return {
        "returns_by_scenario": [
            {"scenario": "Bear Case", "irr_pct": 5.0, "moic_x": 1.2},
            {"scenario": "Base Case", "irr_pct": 14.0, "moic_x": 2.0},
            {"scenario": "Bull Case", "irr_pct": 28.0, "moic_x": 3.2},
        ]
    }


def test_sensitivity_prompt_book_listed() -> None:
    system = compose_system("sensitivity_analysis", sector="EV", geography="India")
    assert "sensitivity_analysis" in listed_agents()
    assert "break" in system.lower() or "grid" in system.lower()
    assert "deal perimeter" in system.lower() or "[DEAL_PERIMETER]" not in system
    body = agent_prompt("sensitivity_analysis")
    assert "Ola" not in body and "SoftBank" not in body
    assert "median" not in body.lower() or "rank" in body.lower()
    assert "invest" in body.lower() or "pass" in body.lower()
    assert "highly sensitive" in body.lower()
    assert "as-of" in body.lower() or "earnings basis" in body.lower()
    assert "questions" in body.lower()
    assert "covenant" in body.lower() or "cash" in body.lower()


def test_sensitivity_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_sensitivity_analysis.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"


def test_grid_direction_check() -> None:
    grid = _parse_grid(_sens_corpus())
    assert grid.get("base_wacc_pct") == 9.0
    assert grid.get("base_terminal_growth_pct") == 3.0
    assert len(grid.get("rows") or []) >= 5
    direction = _direction_check(grid)
    assert direction["status"] == "pass"
    assert direction.get("wacc_direction_ok") is True
    assert direction.get("growth_direction_ok") is True

    # Broken grid: value rises with WACC
    bad = {
        "growth_axis_pct": [1.0, 2.0, 3.0],
        "base_wacc_pct": 9.0,
        "base_terminal_growth_pct": 2.0,
        "rows": [
            {"wacc_pct": 8.0, "values_list": [10.0, 11.0, 12.0]},
            {"wacc_pct": 9.0, "values_list": [20.0, 21.0, 22.0]},
            {"wacc_pct": 10.0, "values_list": [30.0, 31.0, 32.0]},
        ],
    }
    assert _direction_check(bad)["status"] == "fail"


def test_returns_arithmetic_consistent() -> None:
    ok = _check_returns(moic=2.0, irr_pct=14.87, hold_years=5.0)
    assert ok["status"] == "pass"
    bad = _check_returns(moic=2.0, irr_pct=40.0, hold_years=5.0)
    assert bad["status"] == "fail"


def test_heuristic_ranks_and_cases() -> None:
    val = _heuristic_valuation_modeling_spec(
        company="Test3",
        corpus="FY2024E Revenue USD 590M. WACC (Base) 9.0%. Enterprise Value (DCF) 2.55B.",
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        legacy_spec=_valuation_legacy(),
    )
    sens = _heuristic_sensitivity_spec(
        company="Test3",
        corpus=_sens_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        valuation_spec=val,
        recommendation_spec=_recommendation(),
    )
    ranked = sens.get("ranked_drivers") or []
    assert ranked
    assert ranked[0].get("rank") == 1
    assert ranked[0].get("absolute_move") is not None
    grid = sens.get("two_driver_grid") or {}
    assert (grid.get("direction_check") or {}).get("status") == "pass"
    base = grid.get("base_cell") or {}
    assert base.get("consistent_with_valuation_agent") is True
    cases = sens.get("scenario_cases") or []
    assert len(cases) >= 3
    for c in cases:
        assert c.get("growth_assumption")
        assert c.get("capital_assumption")
        # Not adjective-only
        assert "optimistic outlook" not in str(c.get("growth_assumption") or "").lower() or "TG" in str(
            c.get("growth_assumption")
        )
    breakevens = sens.get("breakevens") or []
    assert breakevens
    assert any("operating" in str(b.get("operating_terms") or "").lower() or b.get("condition") for b in breakevens)
    evidence = sens.get("evidence_register") or []
    assert any(e.get("classification") == "evidenced" for e in evidence if isinstance(e, dict))
    assert any(e.get("classification") in {"judgement", "mixed"} for e in evidence if isinstance(e, dict))
    assert sens.get("quality_verdict") in {"PASS", "REWORK"}
    assert sens.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_render_no_invest() -> None:
    sens = _heuristic_sensitivity_spec(
        company="Test3",
        corpus=_sens_corpus() + " We recommend invest.",
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        valuation_spec={"dcf": _valuation_legacy()["dcf"]},
        recommendation_spec=_recommendation(),
    )
    md = render_sensitivity_analysis_markdown("Sensitivity Analysis", sens)
    assert "## 1. Ranked Drivers" in md
    assert "## 2. Two-Driver Grid" in md
    assert "## 3. Downside / Base / Upside Cases" in md
    assert "## 4. Break-even Conditions" in md
    assert "## 5. Evidenced vs Judgement" in md
    assert "## 6. Sensitivity Evidence QA" in md
    assert "## 7. Questions and Inputs Required" in md
    assert "## 8. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()
    assert "direction" in md.lower()


def test_valuation_document_embeds_sensitivity() -> None:
    val = _heuristic_valuation_modeling_spec(
        company="Test3",
        corpus="FY2024E Revenue USD 590M. WACC (Base) 9.0%.",
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        legacy_spec=_valuation_legacy(),
    )
    sens = _heuristic_sensitivity_spec(
        company="Test3",
        corpus=_sens_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        valuation_spec=val,
        recommendation_spec=_recommendation(),
    )
    val["sensitivity_analysis"] = sens
    md = render_valuation_modeling_markdown("Valuation Model", val)
    assert "## 1. Declared Earnings Basis" in md
    assert "# Sensitivity Analysis" in md
    assert "## 1. Ranked Drivers" in md
    assert md.index("# Sensitivity Analysis") > md.index("## 8. Quality & Reliance")


def test_render_agent_document_dispatch_includes_sensitivity() -> None:
    val = _heuristic_valuation_modeling_spec(
        company="Test3",
        corpus="FY2024E Revenue USD 590M. WACC (Base) 9.0%.",
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        legacy_spec=_valuation_legacy(),
    )
    val["sensitivity_analysis"] = _heuristic_sensitivity_spec(
        company="Test3",
        corpus=_sens_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        valuation_spec=val,
    )
    output = {
        "agent_key": "valuation_modeling",
        "agentName": "Valuation Model",
        "target_company": "Test3",
        "sources": ["13_Valuation_Retention_Comparable_Analysis.pdf"],
        "spec": val,
    }
    md = render_agent_document("valuation_modeling", output)
    assert "# Sensitivity Analysis" in md or "## 1. Declared Earnings Basis" in md


def test_build_prefers_heuristic() -> None:
    deal = _FakeDeal()
    spec = build_sensitivity_analysis_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_sens_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        valuation_spec={"dcf": _valuation_legacy()["dcf"]},
        recommendation_spec=_recommendation(),
        prefer_heuristic=True,
    )
    assert spec.get("composer") == "heuristic_v1"
    assert (spec.get("two_driver_grid") or {}).get("direction_check", {}).get("status") == "pass"
    assert "deal_slots" in spec
    assert spec.get("valuation_basis_binding")


def test_valuation_basis_binding_and_qa() -> None:
    sens = _heuristic_sensitivity_spec(
        company="Test3",
        corpus=_sens_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        valuation_spec={
            "dcf": _valuation_legacy()["dcf"],
            "earnings_basis": {
                "metric": "Adj. EBITDA",
                "period": "FY2024E",
                "as_of_date": "2024-03-31",
            },
        },
        recommendation_spec=_recommendation(),
        cash_flow_spec={
            "liquidity": {"pressure": "verified_tight", "runway_months_computed": 4.0},
        },
        capital_structure_spec={
            "covenants": [
                {"covenant": "Net leverage", "threshold": "4.0x", "headroom": "0.6x"},
            ],
        },
        deal_slots={"as_of_date": "2024-03-31", "review_periods": "FY2022–FY2024E"},
    )
    basis = sens.get("valuation_basis_binding") or {}
    assert basis.get("bound") is True
    assert "2024" in str(basis.get("as_of_date") or "")
    be = sens.get("breakevens") or []
    assert any("covenant" in str(b.get("metric") or "").lower() for b in be if isinstance(b, dict))
    assert any("cash" in str(b.get("metric") or "").lower() or "runway" in str(b.get("metric") or "").lower() for b in be if isinstance(b, dict))
    qa = {
        r.get("check"): r
        for r in (sens.get("sensitivity_evidence_qa") or [])
        if isinstance(r, dict)
    }
    assert "valuation_basis_binding" in qa
    assert "one_at_a_time_ranks_computed" in qa
    assert "two_driver_grid_direction" in qa
    assert "no_highly_sensitive_without_compute" in qa
    assert qa["two_driver_grid_direction"]["status"] == "PASS"
    assert qa["no_highly_sensitive_without_compute"]["status"] == "PASS"
    assert sens.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_no_highly_sensitive_without_compute_fails() -> None:
    sens = _heuristic_sensitivity_spec(
        company="Test3",
        corpus=_sens_corpus() + " Valuation is highly sensitive to WACC without sizing.",
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        valuation_spec={"dcf": _valuation_legacy()["dcf"]},
        recommendation_spec=_recommendation(),
    )
    qa = {
        r.get("check"): r
        for r in (sens.get("sensitivity_evidence_qa") or [])
        if isinstance(r, dict)
    }
    assert qa.get("no_highly_sensitive_without_compute", {}).get("status") == "FAIL"
    assert sens.get("questions")
    # Open QA FAILs must not leave READY
    if sens.get("reliance_verdict") == "READY":
        raise AssertionError("READY must be capped when QA FAILs")
    assert sens.get("reliance_verdict") in {"LIMITED", "BLOCKED"}
